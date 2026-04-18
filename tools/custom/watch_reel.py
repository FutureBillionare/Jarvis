"""
Tool: watch_reel
Description: Downloads a video/reel from a URL (Instagram, TikTok, YouTube Shorts, etc.),
extracts frames and audio, transcribes speech, and analyzes with Claude vision.
Returns a full summary of what was seen and heard.
"""

import os
import sys
import json
import base64
import tempfile
import subprocess
import shutil
from pathlib import Path

import imageio_ffmpeg

TOOL_DEFINITION = {
    "name": "watch_reel",
    "description": (
        "Download and analyze a video reel from a URL (Instagram, TikTok, YouTube Shorts, etc.). "
        "Extracts frames and audio, transcribes speech with Whisper, and analyzes with Claude vision. "
        "Returns a full description of everything seen and heard in the video."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL of the reel or short video to watch and analyze"
            },
            "focus": {
                "type": "string",
                "description": "Optional: what to focus on when analyzing (e.g. 'the workout moves', 'the recipe steps', 'the code being shown')"
            },
            "fps": {
                "type": "integer",
                "description": "Frames per second to extract for analysis (default: 1). Use 2-4 for fast-moving content."
            }
        },
        "required": ["url"]
    }
}


def _get_ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()


def _download_video(url: str, out_dir: str) -> str:
    """Download video using yt-dlp. Returns path to downloaded file."""
    out_template = os.path.join(out_dir, "video.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--output", out_template,
        "--quiet",
        "--no-warnings",
        "--ffmpeg-location", os.path.dirname(_get_ffmpeg()),
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()[:500]}")

    # Find downloaded file
    for f in Path(out_dir).iterdir():
        if f.name.startswith("video."):
            return str(f)
    raise RuntimeError("yt-dlp ran but no video file found in output dir")


def _extract_frames(video_path: str, out_dir: str, fps: int = 1) -> list[str]:
    """Extract frames as JPEGs using ffmpeg."""
    ffmpeg = _get_ffmpeg()
    frame_pattern = os.path.join(out_dir, "frame_%04d.jpg")
    cmd = [
        ffmpeg,
        "-i", video_path,
        "-vf", f"fps={fps},scale=960:-1",
        "-q:v", "3",
        frame_pattern,
        "-y", "-loglevel", "error"
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    frames = sorted(Path(out_dir).glob("frame_*.jpg"))
    return [str(f) for f in frames]


def _extract_audio(video_path: str, out_dir: str) -> str | None:
    """Extract audio as WAV for Whisper."""
    ffmpeg = _get_ffmpeg()
    audio_path = os.path.join(out_dir, "audio.wav")
    cmd = [
        ffmpeg,
        "-i", video_path,
        "-ar", "16000", "-ac", "1", "-vn",
        audio_path,
        "-y", "-loglevel", "error"
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
        return audio_path
    return None


def _transcribe(audio_path: str) -> str:
    """Transcribe audio with local Whisper."""
    try:
        import whisper, shutil
        # Ensure bundled ffmpeg is on PATH so Whisper can find it
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)
        ffmpeg_plain = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        if not os.path.exists(ffmpeg_plain):
            shutil.copy(ffmpeg_exe, ffmpeg_plain)
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, fp16=False)
        return result.get("text", "").strip()
    except Exception as e:
        return f"[transcription unavailable: {e}]"


def _analyze_frames_with_claude(frames: list[str], transcript: str, focus: str) -> str:
    """Send frames + transcript to Claude vision via Anthropic API."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Cap at 20 frames to stay within API limits
    sampled = frames
    if len(frames) > 20:
        step = len(frames) / 20
        sampled = [frames[int(i * step)] for i in range(20)]

    content = []

    # Add frames as images
    for i, frame_path in enumerate(sampled):
        with open(frame_path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_data
            }
        })
        content.append({
            "type": "text",
            "text": f"[Frame {i+1}/{len(sampled)}]"
        })

    # Add transcript if available
    focus_line = f"\nFocus especially on: {focus}" if focus else ""
    prompt = (
        f"I am showing you {len(sampled)} frames extracted from a video reel "
        f"({len(frames)} total frames at 1fps).{focus_line}\n\n"
    )
    if transcript and not transcript.startswith("[transcription unavailable"):
        prompt += f"Audio transcript:\n\"{transcript}\"\n\n"
    prompt += (
        "Please give a thorough description of:\n"
        "1. What is happening visually (step by step if it's a tutorial/demo)\n"
        "2. Key text, numbers, or labels visible on screen\n"
        "3. Any important spoken content from the transcript\n"
        "4. A concise summary of the main takeaway or actionable info"
    )
    content.append({"type": "text", "text": prompt})

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": content}]
    )
    return response.content[0].text


def run(params: dict) -> str:
    url = params["url"]
    focus = params.get("focus", "")
    fps = params.get("fps", 1)

    tmp = tempfile.mkdtemp(prefix="watch_reel_")
    try:
        # Step 1: Download
        video_path = _download_video(url, tmp)

        # Step 2: Extract frames + audio in parallel concepts (sequential here)
        frames = _extract_frames(video_path, tmp, fps=fps)
        if not frames:
            return "Error: no frames could be extracted from the video."

        audio_path = _extract_audio(video_path, tmp)

        # Step 3: Transcribe
        transcript = ""
        if audio_path:
            transcript = _transcribe(audio_path)

        # Step 4: Analyze
        analysis = _analyze_frames_with_claude(frames, transcript, focus)

        header = f"[watch_reel] Analyzed {len(frames)} frames"
        if transcript and not transcript.startswith("["):
            header += f" + audio transcript ({len(transcript.split())} words)"
        header += "\n\n"

        return header + analysis

    except Exception as e:
        return f"Error watching reel: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TOOLS = [(TOOL_DEFINITION, run)]
