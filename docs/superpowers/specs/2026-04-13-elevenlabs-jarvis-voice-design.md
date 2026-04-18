# ElevenLabs JARVIS Voice — Design Spec
*2026-04-13*

## Goal

Replace HUBERT's robotic `en-US-ChristopherNeural` edge-tts voice with ElevenLabs TTS using a deep, authoritative British male voice (Daniel by default, swappable to a community JARVIS clone). Graceful fallback to `en-GB-RyanNeural` → pyttsx3 if ElevenLabs is unavailable or quota is exceeded.

---

## Architecture

Three-tier TTS fallback chain:

```
ElevenLabs API (primary) → en-GB-RyanNeural edge-tts (fallback) → pyttsx3 (last resort)
```

The ElevenLabs call slots into the existing `_tts_enqueue` queue system — no threading or queue changes. It runs inside the same `_play()` closure that edge-tts currently uses, just as the first branch tried before falling through.

The API key and voice ID are stored in `jarvis_config.json` (gitignored). If ElevenLabs raises any exception (network error, quota exceeded, bad key), the code falls through to edge-tts silently — no crash, no user-facing error.

---

## Components

### `jarvis_config.json` (modified)

Two new keys added on first `speak()` call if missing:

```json
{
  "elevenlabs_api_key": "<key>",
  "elevenlabs_voice_id": "onwK4e9ZLuTAKqWW03F9"
}
```

- `onwK4e9ZLuTAKqWW03F9` = Daniel — deep, authoritative British male (ElevenLabs built-in)
- Voice ID is swappable: to use a community JARVIS clone, add the voice at elevenlabs.io/voice-library and paste its ID here

### `App.speak()` (modified, `main.py`)

The `_play()` closure inside `speak()` gains a new first branch:

```
1. Read elevenlabs_api_key + elevenlabs_voice_id from jarvis_config.json
2. If key missing → skip ElevenLabs, go to edge-tts
3. POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
   Body: {
     "text": text,
     "model_id": "eleven_turbo_v2_5",
     "voice_settings": {
       "stability": 0.45,
       "similarity_boost": 0.85,
       "style": 0.35,
       "use_speaker_boost": true
     }
   }
   Header: xi-api-key: <key>
4. On 200: save response bytes to temp .mp3, play via existing pygame path
5. On any exception: fall through to en-GB-RyanNeural edge-tts branch
```

**Model:** `eleven_turbo_v2_5` — lowest latency ElevenLabs model, high quality.

**Voice settings rationale:**
- `stability: 0.45` — slightly expressive, not flat
- `similarity_boost: 0.85` — stays close to the voice character
- `style: 0.35` — measured, authoritative delivery
- `use_speaker_boost: true` — enhances voice clarity

### edge-tts fallback (modified)

The existing `en-US-ChristopherNeural` call changes to `en-GB-RyanNeural` so even the fallback is British.

---

## File Changes

| File | Change |
|------|--------|
| `main.py` — `App.speak()` | Add ElevenLabs branch before edge-tts; change edge-tts voice to en-GB-RyanNeural |
| `jarvis_config.json` | Add `elevenlabs_api_key` and `elevenlabs_voice_id` keys |

No new files. No other files touched.

---

## Spec Self-Review

- **Placeholder scan:** No TBDs. API endpoint, model ID, voice settings, and voice ID all explicit.
- **Consistency:** `jarvis_config.json` is the single source for key and voice ID — no hardcoding in `speak()`.
- **Scope:** One method modified (`speak()`), one config file updated. Appropriately bounded.
- **Ambiguity:** "Fall through on any exception" — covers `requests.exceptions.*`, `json.JSONDecodeError`, HTTP non-200, quota errors (HTTP 429). All caught by a bare `except Exception`.
