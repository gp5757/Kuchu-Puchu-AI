"""
core/video_summary package
AI-Powered Whiteboard Video Summary Generator for Kuchu Puchu AI.
"""

from core.video_summary.manager import create_job, get_job, run_video_generation_job
from core.video_summary.storyboard import generate_storyboard
from core.video_summary.tts_engine import synthesize_speech, resolve_voice, VOICE_MAP

__all__ = [
    "create_job",
    "get_job",
    "run_video_generation_job",
    "generate_storyboard",
    "synthesize_speech",
    "resolve_voice",
    "VOICE_MAP"
]
