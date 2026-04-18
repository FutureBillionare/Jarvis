"""
Tool: edge_tts_speak
Description: Speak text aloud using edge-tts (en-US-GuyNeural). Falls back to pyttsx3 if edge-tts is unavailable.
"""

TOOL_DEFINITION = {
    "name": "edge_tts_speak",
    "description": "Speak text aloud using edge-tts (Microsoft neural TTS, en-US-GuyNeural voice). Falls back to pyttsx3 if edge-tts or audio backend is unavailable.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to speak aloud"
            }
        },
        "required": ["text"]
    }
}


def run(params: dict) -> str:
    text = params["text"]

    try:
        import asyncio, tempfile, os
        import edge_tts

        async def _synth():
            tts = edge_tts.Communicate(text, "en-US-GuyNeural")
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp = f.name
            await tts.save(tmp)
            return tmp

        tmp = asyncio.run(_synth())
        try:
            import sounddevice as sd
            from pydub import AudioSegment
            import numpy as np
            seg  = AudioSegment.from_mp3(tmp)
            pcm  = np.array(seg.get_array_of_samples(), dtype=np.float32)
            pcm /= 2 ** (seg.sample_width * 8 - 1)
            if seg.channels == 2:
                pcm = pcm.reshape(-1, 2)
            sd.play(pcm, seg.frame_rate)
            sd.wait()
            return f"Spoke via edge-tts: {text[:80]}"
        except Exception:
            try:
                import pygame, time
                pygame.mixer.init()
                pygame.mixer.music.load(tmp)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                return f"Spoke via edge-tts+pygame: {text[:80]}"
            except Exception as e:
                raise e
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    except Exception:
        # Final fallback: pyttsx3
        try:
            import pyttsx3
            e = pyttsx3.init()
            e.setProperty("rate", 175)
            e.say(text)
            e.runAndWait()
            return f"Spoke via pyttsx3 (fallback): {text[:80]}"
        except Exception as err:
            return f"Speech failed: {err}"


TOOLS = [(TOOL_DEFINITION, run)]
