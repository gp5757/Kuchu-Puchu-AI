"""
core/video_summary/assembler.py
Assembles scene keyframes and narration audio into web-optimized H.264 MP4 videos
using FFmpeg with progressive whiteboard reveals.
"""

import os
import shutil
import subprocess
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
    Stages:
      Stage 0 (Canvas + Header): First 15% of narration
      Stage 1 (Badge + Doodle): Next 30% of narration
      Stage 2 (Key Point Card): Next 30% of narration
      Stage 3 (Bullet Points): Final 25% of narration
    """
    os.makedirs(temp_dir, exist_ok=True)
    scene_id = scene_data.get("scene_id", 1)

    # Calculate stage durations
    total_dur = max(duration, 4.0)
    dur_0 = round(total_dur * 0.15, 2)
    dur_1 = round(total_dur * 0.30, 2)
    dur_2 = round(total_dur * 0.30, 2)
    dur_3 = round(max(1.0, total_dur - (dur_0 + dur_1 + dur_2)), 2)

    stage_files = []
    for stage_idx in range(4):
        frame_img = render_scene_frame(scene_data, video_title, total_scenes, stage=stage_idx)
        frame_path = os.path.join(temp_dir, f"s{scene_id}_stage_{stage_idx}.png")
        frame_img.save(frame_path, "PNG")
        stage_files.append(frame_path)

    # Concat file for FFmpeg
    concat_txt_path = os.path.join(temp_dir, f"s{scene_id}_concat.txt")
    with open(concat_txt_path, "w", encoding="utf-8") as f:
        # Note: in FFmpeg concat format, forward slashes avoid escaping bugs
        f.write(f"file '{stage_files[0].replace(os.sep, '/')}'\n")
        f.write(f"duration {dur_0}\n")
        f.write(f"file '{stage_files[1].replace(os.sep, '/')}'\n")
        f.write(f"duration {dur_1}\n")
        f.write(f"file '{stage_files[2].replace(os.sep, '/')}'\n")
        f.write(f"duration {dur_2}\n")
        f.write(f"file '{stage_files[3].replace(os.sep, '/')}'\n")
        f.write(f"duration {dur_3}\n")
        f.write(f"file '{stage_files[3].replace(os.sep, '/')}'\n")

    # Mux frames + audio into scene MP4
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_txt_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-r", "25",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_scene_mp4
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_scene_mp4


def concatenate_scenes(scene_mp4_paths: list, final_output_mp4: str, temp_dir: str) -> str:
    """Concatenates all individual scene MP4s into a single seamless final MP4."""
    os.makedirs(os.path.dirname(os.path.abspath(final_output_mp4)), exist_ok=True)

    if not scene_mp4_paths:
        raise ValueError("No scene clips provided to concatenate.")

    if len(scene_mp4_paths) == 1:
        shutil.copyfile(scene_mp4_paths[0], final_output_mp4)
        return final_output_mp4

    list_file_path = os.path.join(temp_dir, "scenes_list.txt")
    with open(list_file_path, "w", encoding="utf-8") as f:
        for p in scene_mp4_paths:
            f.write(f"file '{p.replace(os.sep, '/')}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        final_output_mp4
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return final_output_mp4
