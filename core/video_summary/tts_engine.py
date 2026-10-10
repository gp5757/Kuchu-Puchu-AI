"""
core/video_summary/tts_engine.py
Text-to-speech module using Microsoft Edge-TTS with Sarvam AI fallback,
providing clean neural audio narration and exact duration timing.
"""

import os
import asyncio
import subprocess
import requests
from utils.audio_processor import get_ffmpeg_binary
from dotenv import load_dotenv

load_dotenv()

VOICE_MAP = {
    "christopher": "en-US-ChristopherNeural",   # Natural US Male
    "jenny": "en-US-JennyNeural",               # Warm US Female
    "neerja": "en-IN-NeerjaNeural",             # Expressive Indian English Female
    "prabhat": "en-IN-PrabhatNeural",           # Professional Indian English Male
    "swara": "hi-IN-SwaraNeural",               # Hindi Female
    "madhur": "hi-IN-MadhurNeural",             # Hindi Male
}

DEFAULT_VOICE = "en-US-ChristopherNeural"


def resolve_voice(voice_key: str) -> str:
    """Resolves user choice or identifier to an actual Edge-TTS voice name."""
    if not voice_key:
        return DEFAULT_VOICE
    key_lower = voice_key.lower().strip()
    return VOICE_MAP.get(key_lower, voice_key)


async def synthesize_speech(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> float:
    """
    Synthesizes narration audio from text and saves to output_path (.mp3).
    Returns exact duration of the generated audio in seconds.
    """
    clean_text = text.strip()
    if not clean_text:
        clean_text = "Key concept overview."

    resolved_voice = resolve_voice(voice)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # 1. Primary: Edge-TTS
    try:
        import edge_tts
        communicate = edge_tts.Communicate(clean_text, resolved_voice)
        await communicate.save(output_path)
        duration = get_audio_duration(output_path)
        if duration > 0.5:
            return duration
    except Exception as e:
        print(f"[tts_engine] Edge-TTS warning for '{resolved_voice}': {e}. Attempting fallback...")

    # 2. Secondary: Sarvam AI if Hindi / Hinglish and key available
    sarvam_key = os.getenv("SARVAM_API_KEY")
    if sarvam_key and ("hi-IN" in resolved_voice or "en-IN" in resolved_voice):
        try:
            sarvam_dur = _synthesize_sarvam(clean_text, output_path, sarvam_key)
            if sarvam_dur > 0.5:
                return sarvam_dur
        except Exception as e:
            print(f"[tts_engine] Sarvam TTS fallback warning: {e}")

    # 3. Emergency fallback: Generate small silence clip so video rendering never crashes
    return _generate_silent_audio(output_path, duration_sec=5.0)


def _synthesize_sarvam(text: str, output_path: str, api_key: str) -> float:
    """Synthesizes speech using Sarvam TTS API."""
    import base64
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": [text[:500]],
        "target_language_code": "hi-IN",
        "speaker": "meera",
        "pitch": 0,
        "pace": 1.0,
        "loudness": 1.5,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
        "model": "bulbul:v1"
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        audios = data.get("audios", [])
        if audios:
            raw_b64 = audios[0]
            audio_bytes = base64.b64decode(raw_b64)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            return get_audio_duration(output_path)
    raise RuntimeError(f"Sarvam TTS failed with status {resp.status_code}")


def _generate_silent_audio(output_path: str, duration_sec: float = 5.0) -> float:
    """Generates a brief silent mp3 using ffmpeg as a zero-crash safety net."""
    ffmpeg_bin = get_ffmpeg_binary() or "ffmpeg"
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(duration_sec),
        "-q:a", "9",
        "-acodec", "libmp3lame",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return duration_sec
    except Exception as e:
        print(f"[tts_engine] Failed to generate silence: {e}")
        return duration_sec


def get_audio_duration(file_path: str) -> float:
    """Extracts duration of audio file in seconds via ffprobe or pydub."""
    if not os.path.exists(file_path):
        return 0.0

    # Try ffprobe first
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        dur_str = result.stdout.strip()
        if dur_str:
            return round(float(dur_str), 2)
    except Exception:
        pass

    # Fallback to pydub
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(file_path)
        return round(len(seg) / 1000.0, 2)
    except Exception:
        pass

    return 5.0
