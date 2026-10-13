"""
core/video_summary/assembler.py
Assembles scene keyframes and narration audio into web-optimized H.264 MP4 videos
using FFmpeg with progressive whiteboard reveals, pristine AV sync, and fast stream-copy muxing.
"""

import os
import shutil
import subprocess
from utils.audio_processor import get_ffmpeg_binary
from core.video_summary.renderer import render_scene_frame


def assemble_scene_video(
    scene_data: dict,
    video_title: str,
    total_scenes: int,
    audio_path: str,
    duration: float,
    output_scene_mp4: str,
    temp_dir: str
) -> str:
    """
    Renders progressive reveal frames for a scene and muxes with the scene's narration audio.
    Ensures precise audio-video synchronization without clipped syllables or frozen tails.
    Stages:
      Stage 0 (Canvas + Header): First 15% of narration
      Stage 1 (Badge + Doodle): Next 30% of narration
      Stage 2 (Key Point Card): Next 30% of narration
      Stage 3 (Bullet Points): Final 25% of narration + natural ending buffer
    """
    os.makedirs(temp_dir, exist_ok=True)
    scene_id = scene_data.get("scene_id", 1)

    # Audio padding (0.25s) ensures the last spoken word is never truncated by frame rounding
    total_dur = max(duration + 0.25, 4.0)
    dur_0 = round(total_dur * 0.15, 2)
    dur_1 = round(total_dur * 0.30, 2)
    dur_2 = round(total_dur * 0.30, 2)
    dur_3 = max(1.0, round(total_dur - (dur_0 + dur_1 + dur_2), 2))

    stage_files = []
    for stage_idx in range(4):
        frame_img = render_scene_frame(scene_data, video_title, total_scenes, stage=stage_idx)
        frame_path = os.path.join(temp_dir, f"s{scene_id}_stage_{stage_idx}.png")
        frame_img.save(frame_path, "PNG")
        stage_files.append(frame_path)

    # Concat file for FFmpeg (filenames relative to temp_dir)
    concat_txt_path = os.path.join(temp_dir, f"s{scene_id}_concat.txt")
    f0 = os.path.basename(stage_files[0])
    f1 = os.path.basename(stage_files[1])
    f2 = os.path.basename(stage_files[2])
    f3 = os.path.basename(stage_files[3])
    with open(concat_txt_path, "w", encoding="utf-8") as f:
        f.write(f"file '{f0}'\n")
        f.write(f"duration {dur_0}\n")
        f.write(f"file '{f1}'\n")
        f.write(f"duration {dur_1}\n")
        f.write(f"file '{f2}'\n")
        f.write(f"duration {dur_2}\n")
        f.write(f"file '{f3}'\n")
        f.write(f"duration {dur_3}\n")
        f.write(f"file '{f3}'\n")

    ffmpeg_bin = get_ffmpeg_binary() or "ffmpeg"
    # Mux frames + audio into scene MP4 with standardized rate and timestamps
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_txt_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-r", "25",
        "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        output_scene_mp4
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45, check=True)
    return output_scene_mp4


def concatenate_scenes(scene_mp4_paths: list, final_output_mp4: str, temp_dir: str) -> str:
    """
    Concatenates individual scene MP4s into a single seamless final MP4.
    Uses video stream-copy (-c:v copy) to eliminate CPU re-encoding overhead and finish in < 1 second.
    """
    os.makedirs(os.path.dirname(os.path.abspath(final_output_mp4)), exist_ok=True)

    if not scene_mp4_paths:
        raise ValueError("No scene clips provided to concatenate.")

    # Filter only existing scenes
    valid_paths = [p for p in scene_mp4_paths if os.path.exists(p) and os.path.getsize(p) > 1000]
    if not valid_paths:
        raise RuntimeError("All rendered scene video files are missing or empty.")

    if len(valid_paths) == 1:
        shutil.copyfile(valid_paths[0], final_output_mp4)
        return final_output_mp4

    list_file_path = os.path.join(temp_dir, "scenes_list.txt")
    with open(list_file_path, "w", encoding="utf-8") as f:
        for p in valid_paths:
            # Use relative filename so concat demuxer avoids absolute path escaping issues across OSes
            f.write(f"file '{os.path.basename(p)}'\n")

    ffmpeg_bin = get_ffmpeg_binary() or "ffmpeg"
    # Copy video stream directly without re-encoding; clean audio remuxing ensures seamless cross-scene audio
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "scenes_list.txt",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-movflags", "+faststart",
        os.path.abspath(final_output_mp4)
    ]

    try:
        subprocess.run(
            cmd,
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=True
        )
    except Exception as copy_err:
        err_msg = ""
        if hasattr(copy_err, "stderr") and copy_err.stderr:
            err_msg = copy_err.stderr.decode("utf-8", errors="ignore")
        print(f"[assembler] Notice: Stream copy concat returned: {err_msg or copy_err}. Retrying with fast re-encode...")

        # Resilient fallback with fastest CPU preset
        fallback_cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", "scenes_list.txt",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            "-movflags", "+faststart",
            os.path.abspath(final_output_mp4)
        ]
        res = subprocess.run(
            fallback_cmd,
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45
        )
        if res.returncode != 0:
            err_txt = res.stderr.decode("utf-8", errors="ignore") if res.stderr else "Unknown FFmpeg error"
            raise RuntimeError(f"FFmpeg concatenation failed: {err_txt[:300]}")

    if not os.path.exists(final_output_mp4) or os.path.getsize(final_output_mp4) < 1000:
        raise RuntimeError(f"Concatenated final video file missing or corrupted at {final_output_mp4}")

    return final_output_mp4
