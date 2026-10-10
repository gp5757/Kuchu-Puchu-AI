"""
core/video_summary/manager.py
Orchestrator for managing background video summary jobs with real-time status tracking,
progress reporting, and automatic asset cleanup.
"""

import os
import time
import uuid
import shutil
import asyncio
from core.video_summary.storyboard import generate_storyboard
from core.video_summary.tts_engine import synthesize_speech, resolve_voice
from core.video_summary.assembler import assemble_scene_video, concatenate_scenes

_jobs = {}
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
    """Executes the full end-to-end video summary generation in background."""
    job = _jobs.get(job_id)
    if not job:
        return

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
        job["progress"] = 30
        job["message"] = f"Storyboard created with {len(scenes)} scenes! Recording voiceover..."

        # Step 2: Synthesize TTS Audio (Progress: 30% -> 60%)
        job["stage"] = "narration"
        resolved_voice = resolve_voice(voice)
        audio_files = []
        durations = []

        for idx, scene in enumerate(scenes, 1):
            narration_text = scene.get("narration", "")
            audio_out = os.path.join(temp_job_dir, f"audio_scene_{idx}.mp3")
            dur = await synthesize_speech(narration_text, audio_out, voice=resolved_voice)
            audio_files.append(audio_out)
            durations.append(dur)
            pct = 30 + int((idx / len(scenes)) * 25)
            job["progress"] = pct
            job["message"] = f"Narrating scene {idx} of {len(scenes)}..."

        # Step 3: Render and Assemble Scene Videos (Progress: 60% -> 85%)
        job["stage"] = "rendering"
        scene_mp4_paths = []
        for idx, (scene, audio_path, dur) in enumerate(zip(scenes, audio_files, durations), 1):
            job["progress"] = 60 + int((idx / len(scenes)) * 25)
            job["message"] = f"Sketching whiteboard frames for scene {idx} of {len(scenes)}..."
            scene_mp4 = os.path.join(temp_job_dir, f"scene_{idx}.mp4")
            
            await asyncio.to_thread(
                assemble_scene_video,
                scene,
                title,
                len(scenes),
                audio_path,
                dur,
                scene_mp4,
                temp_job_dir
            )
            scene_mp4_paths.append(scene_mp4)

        # Step 4: Concatenate into Final Web-Optimized MP4 (Progress: 85% -> 98%)
        job["stage"] = "encoding"
        job["progress"] = 90
        job["message"] = "Muxing final high-definition MP4..."

        final_mp4 = os.path.join(VIDEOS_DIR, f"video_summary_{job_id}.mp4")
        await asyncio.to_thread(
            concatenate_scenes, scene_mp4_paths, final_mp4, temp_job_dir
        )

        job["video_path"] = final_mp4
        job["status"] = "completed"
        job["stage"] = "ready"
        job["progress"] = 100
        job["message"] = "Whiteboard video summary generated successfully!"

    except Exception as e:
        import traceback
        traceback.print_exc()
        job["status"] = "failed"
        job["error"] = str(e)
        job["message"] = f"Video generation failed: {str(e)}"
    finally:
        # Cleanup temporary files, keeping final MP4
        try:
            if os.path.exists(temp_job_dir):
                shutil.rmtree(temp_job_dir, ignore_errors=True)
        except Exception:
            pass


def _cleanup_old_jobs():
    """Removes video assets older than 2 hours to conserve disk space."""
    now = time.time()
    cutoff = now - 7200  # 2 hours
    expired_ids = []
    for jid, data in _jobs.items():
        if data.get("created_at", now) < cutoff:
            expired_ids.append(jid)
            vpath = data.get("video_path")
            if vpath and os.path.exists(vpath):
                try:
                    os.remove(vpath)
                except Exception:
                    pass

    for jid in expired_ids:
        _jobs.pop(jid, None)
