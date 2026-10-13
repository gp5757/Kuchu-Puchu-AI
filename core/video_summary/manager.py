"""
core/video_summary/manager.py
Orchestrator for managing background video summary jobs with real-time status tracking,
dynamic parallel processing, progress reporting, and automatic asset cleanup.
"""

import os
import time
import uuid
import shutil
import asyncio
from concurrent.futures import ThreadPoolExecutor
from core.video_summary.storyboard import generate_storyboard
from core.video_summary.tts_engine import synthesize_speech, resolve_voice
from core.video_summary.assembler import assemble_scene_video, concatenate_scenes

_jobs = {}
_active_tasks = set()  # Strong references prevent Python asyncio GC from killing running tasks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIDEOS_DIR = os.path.join(BASE_DIR, "downloads", "video_summaries")
os.makedirs(VIDEOS_DIR, exist_ok=True)


def create_job(title: str, voice: str = "christopher") -> str:
    """Initializes and registers a new video generation job."""
    _cleanup_old_jobs()
    job_id = uuid.uuid4().hex[:10]
    _jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 5,
        "stage": "queued",
        "message": "Queued for storyboard synthesis...",
        "video_path": None,
        "title": title or "Lecture Summary",
        "voice": resolve_voice(voice),
        "scenes_count": 0,
        "error": None,
        "created_at": time.time()
    }
    return job_id


def get_job(job_id: str) -> dict:
    """Returns current job status metadata."""
    return _jobs.get(job_id)


async def run_video_generation_job(
    job_id: str,
    title: str,
    summary: str,
    action_items: str = "",
    key_decisions: str = "",
    voice: str = "christopher"
):
    """
    Executes the full end-to-end video summary generation in background using
    parallel TTS synthesis and parallel scene rendering with an overall 180s watchdog.
    """
    job = _jobs.get(job_id)
    if not job:
        return

    try:
        await asyncio.wait_for(
            _execute_video_generation_job(job_id, title, summary, action_items, key_decisions, voice),
            timeout=180.0
        )
    except asyncio.TimeoutError:
        print(f"[manager] Video summary job {job_id} timed out after 180s.")
        job["status"] = "failed"
        job["error"] = "Video generation timed out after 3 minutes. Please try again with a shorter summary."
        job["message"] = "Video generation timed out after 3 minutes. Please try again."
    except Exception as e:
        import traceback
        traceback.print_exc()
        job["status"] = "failed"
        job["error"] = str(e)
        job["message"] = f"Video generation failed: {str(e)}"


async def _execute_video_generation_job(
    job_id: str,
    title: str,
    summary: str,
    action_items: str = "",
    key_decisions: str = "",
    voice: str = "christopher"
):
    job = _jobs.get(job_id)
    temp_job_dir = os.path.join(VIDEOS_DIR, f"temp_{job_id}")
    os.makedirs(temp_job_dir, exist_ok=True)

    try:
        # Step 1: Generate Storyboard (Progress: 10% -> 25%)
        job["status"] = "processing"
        job["stage"] = "storyboard"
        job["progress"] = 15
        job["message"] = "Synthesizing visual concepts into storyboard..."

        storyboard = await asyncio.to_thread(
            generate_storyboard, title, summary, action_items, key_decisions
        )
        scenes = storyboard.get("scenes", [])
        if not scenes:
            raise RuntimeError("Failed to generate storyboard scenes.")

        job["scenes_count"] = len(scenes)
        job["progress"] = 25
        job["message"] = f"Storyboard created with {len(scenes)} scenes! Recording voiceovers..."

        # Step 2: Concurrent TTS Audio Synthesis (Progress: 25% -> 55%)
        job["stage"] = "narration"
        resolved_voice = resolve_voice(voice)
        completed_tts_count = 0
        state_lock = asyncio.Lock()

        async def synthesize_one_scene(idx: int, scene_data: dict):
            nonlocal completed_tts_count
            narration_text = scene_data.get("narration", "")
            audio_out = os.path.join(temp_job_dir, f"audio_scene_{idx}.mp3")
            dur = await synthesize_speech(narration_text, audio_out, voice=resolved_voice)
            
            async with state_lock:
                completed_tts_count += 1
                pct = 25 + int((completed_tts_count / len(scenes)) * 30)
                job["progress"] = pct
                job["message"] = f"Voiceover ready for {completed_tts_count} of {len(scenes)} scenes..."
            return idx, audio_out, dur

        tts_tasks = [synthesize_one_scene(i, sc) for i, sc in enumerate(scenes, 1)]
        tts_results = await asyncio.gather(*tts_tasks)
        tts_results.sort(key=lambda x: x[0])  # Maintain chronological order

        audio_files = [r[1] for r in tts_results]
        durations = [r[2] for r in tts_results]

        # Step 3: Concurrent Scene Video Rendering (Progress: 55% -> 88%)
        job["stage"] = "rendering"
        job["progress"] = 58
        job["message"] = f"Sketching whiteboard frames for all {len(scenes)} scenes in parallel..."
        completed_render_count = 0

        def render_worker(idx: int, sc_data: dict, a_path: str, dur_val: float):
            scene_mp4 = os.path.join(temp_job_dir, f"scene_{idx}.mp4")
            assemble_scene_video(
                sc_data,
                title,
                len(scenes),
                a_path,
                dur_val,
                scene_mp4,
                temp_job_dir
            )
            return idx, scene_mp4

        async def render_async(idx: int, sc_data: dict, a_path: str, dur_val: float, pool: ThreadPoolExecutor):
            nonlocal completed_render_count
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(pool, render_worker, idx, sc_data, a_path, dur_val)
            async with state_lock:
                completed_render_count += 1
                pct = 58 + int((completed_render_count / len(scenes)) * 30)
                job["progress"] = pct
                job["message"] = f"Rendered scene {completed_render_count} of {len(scenes)}..."
            return res

        workers_count = min(4, len(scenes))
        with ThreadPoolExecutor(max_workers=workers_count) as pool:
            render_tasks = [
                render_async(i, sc, a, d, pool)
                for i, (sc, a, d) in enumerate(zip(scenes, audio_files, durations), 1)
            ]
            render_results = await asyncio.gather(*render_tasks)

        render_results.sort(key=lambda x: x[0])
        scene_mp4_paths = [r[1] for r in render_results]

        # Step 4: Stream-Copy Concatenation into Final MP4 (Progress: 88% -> 100%)
        job["stage"] = "encoding"
        job["progress"] = 92
        job["message"] = "Muxing final high-definition MP4..."

        final_mp4 = os.path.join(VIDEOS_DIR, f"video_summary_{job_id}.mp4")
        await asyncio.to_thread(
            concatenate_scenes, scene_mp4_paths, final_mp4, temp_job_dir
        )

        if not os.path.exists(final_mp4) or os.path.getsize(final_mp4) < 1000:
            raise RuntimeError("Final video MP4 could not be assembled or verified.")

        job["progress"] = 98
        job["message"] = "Finalizing stream..."
        job["video_path"] = final_mp4
        job["status"] = "completed"
        job["stage"] = "ready"
        job["progress"] = 100
        job["message"] = "Whiteboard video summary generated successfully!"

    finally:
        # Cleanup temporary scratch files while preserving the final MP4
        try:
            if os.path.exists(temp_job_dir):
                shutil.rmtree(temp_job_dir, ignore_errors=True)
        except Exception:
            pass


def _cleanup_old_jobs():
    """Removes video assets older than 2 hours to conserve disk space."""
    now = time.time()
    for jid in list(_jobs.keys()):
        job = _jobs[jid]
        if now - job.get("created_at", now) > 7200:
            vpath = job.get("video_path")
            if vpath and os.path.exists(vpath):
                try:
                    os.remove(vpath)
                except Exception:
                    pass
            _jobs.pop(jid, None)
