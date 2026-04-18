# ElevenLabs JARVIS Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace HUBERT's American `en-US-ChristopherNeural` edge-tts voice with ElevenLabs TTS using a British JARVIS-like voice (Daniel by default), with graceful fallback to `en-GB-RyanNeural` → pyttsx3.

**Architecture:** ElevenLabs is added as a new first branch inside the existing `_play()` closure in `App.speak()`. If ElevenLabs fails for any reason (quota, network, bad key), the code falls through to edge-tts which is also updated to use the British `en-GB-RyanNeural` voice. Config (API key + voice ID) is read from `jarvis_config.json` via a new helper in `config.py`.

**Tech Stack:** Python, `requests`, ElevenLabs REST API (`eleven_turbo_v2_5`), `config.py` (existing), `jarvis_config.json` (existing, gitignored)

---

## File Map

| File | Change |
|------|--------|
| `config.py` | Add `get_elevenlabs_config()` and `set_elevenlabs_config()` helpers |
| `tests/test_elevenlabs_config.py` | New — unit tests for the config helpers |
| `main.py` — `App.speak()` (line 3364) | Replace `_play()` body with ElevenLabs-first + en-GB-RyanNeural fallback |
| `jarvis_config.json` | Add `elevenlabs_api_key` and `elevenlabs_voice_id` keys |

---

## Task 1: Add ElevenLabs config helpers to `config.py`

**Files:**
- Modify: `config.py`
- Create: `tests/test_elevenlabs_config.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/jakegoncalves/Jarvis/tests/test_elevenlabs_config.py`:

```python
"""Tests for ElevenLabs config helpers in config.py."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

CONFIG_FILE_ATTR = "CONFIG_FILE"
DEFAULT_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"


def _patch_config(tmp_path, monkeypatch, data: dict):
    """Write data to a temp config file and point config.py at it."""
    import config as cfg_mod
    cfg_file = tmp_path / "jarvis_config.json"
    cfg_file.write_text(json.dumps(data))
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cfg_file)


class TestGetElevenLabsConfig:
    def test_returns_empty_when_no_key(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, {})
        from config import get_elevenlabs_config
        assert get_elevenlabs_config() == {}

    def test_returns_empty_when_key_is_blank(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, {"elevenlabs_api_key": ""})
        from config import get_elevenlabs_config
        assert get_elevenlabs_config() == {}

    def test_returns_key_and_default_voice_id(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, {"elevenlabs_api_key": "sk_test"})
        from config import get_elevenlabs_config
        result = get_elevenlabs_config()
        assert result["api_key"] == "sk_test"
        assert result["voice_id"] == DEFAULT_VOICE_ID

    def test_returns_custom_voice_id(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, {
            "elevenlabs_api_key": "sk_test",
            "elevenlabs_voice_id": "custom_id_123"
        })
        from config import get_elevenlabs_config
        assert get_elevenlabs_config()["voice_id"] == "custom_id_123"


class TestSetElevenLabsConfig:
    def test_writes_key_and_voice_id(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, {})
        import config as cfg_mod
        cfg_mod.set_elevenlabs_config("sk_mykey", "myvoice")
        data = json.loads(cfg_mod.CONFIG_FILE.read_text())
        assert data["elevenlabs_api_key"] == "sk_mykey"
        assert data["elevenlabs_voice_id"] == "myvoice"

    def test_preserves_existing_api_key(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, {"api_key": "sk-ant-existing"})
        import config as cfg_mod
        cfg_mod.set_elevenlabs_config("sk_el", "voice_id")
        data = json.loads(cfg_mod.CONFIG_FILE.read_text())
        assert data["api_key"] == "sk-ant-existing"
        assert data["elevenlabs_api_key"] == "sk_el"

    def test_uses_default_voice_id_when_not_specified(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, {})
        import config as cfg_mod
        cfg_mod.set_elevenlabs_config("sk_mykey")
        data = json.loads(cfg_mod.CONFIG_FILE.read_text())
        assert data["elevenlabs_voice_id"] == DEFAULT_VOICE_ID
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/jakegoncalves/Jarvis && python3 -m pytest tests/test_elevenlabs_config.py -v 2>&1 | head -20
```

Expected: `ImportError` or `AttributeError: module 'config' has no attribute 'get_elevenlabs_config'`

- [ ] **Step 3: Add helpers to `config.py`**

Open `/Users/jakegoncalves/Jarvis/config.py`. Current content:

```python
import os
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "jarvis_config.json"

def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(data: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        cfg = load_config()
        key = cfg.get("api_key", "")
    return key

def set_api_key(key: str):
    cfg = load_config()
    cfg["api_key"] = key
    save_config(cfg)
```

Replace with:

```python
import os
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "jarvis_config.json"

_DEFAULT_EL_VOICE = "onwK4e9ZLuTAKqWW03F9"  # Daniel — British, authoritative


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(data: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        cfg = load_config()
        key = cfg.get("api_key", "")
    return key

def set_api_key(key: str):
    cfg = load_config()
    cfg["api_key"] = key
    save_config(cfg)

def get_elevenlabs_config() -> dict:
    """Return {'api_key': ..., 'voice_id': ...} or {} if not configured."""
    cfg = load_config()
    key = cfg.get("elevenlabs_api_key", "")
    if not key:
        return {}
    return {
        "api_key": key,
        "voice_id": cfg.get("elevenlabs_voice_id", _DEFAULT_EL_VOICE),
    }

def set_elevenlabs_config(api_key: str, voice_id: str = _DEFAULT_EL_VOICE):
    """Save ElevenLabs credentials to jarvis_config.json."""
    cfg = load_config()
    cfg["elevenlabs_api_key"] = api_key
    cfg["elevenlabs_voice_id"] = voice_id
    save_config(cfg)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jakegoncalves/Jarvis && python3 -m pytest tests/test_elevenlabs_config.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Verify existing tests still pass**

```bash
cd /Users/jakegoncalves/Jarvis && python3 -m pytest tests/ -v 2>&1 | tail -10
```

Expected: All tests PASS (31 prior + 7 new = 38 total).

---

## Task 2: Write ElevenLabs credentials to `jarvis_config.json`

**Files:**
- Modify: `jarvis_config.json`

- [ ] **Step 1: Add credentials using the new helper**

Run this one-liner to write the credentials without touching the existing Anthropic key:

```bash
cd /Users/jakegoncalves/Jarvis && python3 -c "
from config import set_elevenlabs_config
set_elevenlabs_config('sk_ad5c6e84975b3c40a85aa76e060290084f7f520b5514e87e')
print('ElevenLabs config written.')
"
```

Expected output: `ElevenLabs config written.`

- [ ] **Step 2: Verify `jarvis_config.json` has both keys**

```bash
python3 -c "import json; d=json.load(open('jarvis_config.json')); print('api_key present:', bool(d.get('api_key'))); print('el_key present:', bool(d.get('elevenlabs_api_key'))); print('voice_id:', d.get('elevenlabs_voice_id'))"
```

Expected:
```
api_key present: True
el_key present: True
voice_id: onwK4e9ZLuTAKqWW03F9
```

---

## Task 3: Update `App.speak()` to use ElevenLabs first

**Files:**
- Modify: `main.py` — `App.speak()` starting at line 3364

- [ ] **Step 1: Replace the `_play()` closure**

In `/Users/jakegoncalves/Jarvis/main.py`, find the `_play()` function inside `App.speak()` (lines ~3380–3450). Replace the entire `def _play():` block (from `def _play():` through `_tts_enqueue(_play)`) with:

```python
        def _play():
            import ui_bridge as _ub
            _ub.push("sphere_speaking", active=True)
            try:
                import tempfile as _tf, os as _os
                from config import get_elevenlabs_config

                tmp = None

                # 1. Try ElevenLabs (primary — British JARVIS voice)
                el_cfg = get_elevenlabs_config()
                if el_cfg:
                    try:
                        import requests as _req
                        resp = _req.post(
                            f"https://api.elevenlabs.io/v1/text-to-speech/{el_cfg['voice_id']}",
                            headers={
                                "xi-api-key": el_cfg["api_key"],
                                "Content-Type": "application/json",
                            },
                            json={
                                "text": text,
                                "model_id": "eleven_turbo_v2_5",
                                "voice_settings": {
                                    "stability": 0.45,
                                    "similarity_boost": 0.85,
                                    "style": 0.35,
                                    "use_speaker_boost": True,
                                },
                            },
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            fd, tmp = _tf.mkstemp(suffix=".mp3")
                            _os.close(fd)
                            with open(tmp, "wb") as _f:
                                _f.write(resp.content)
                    except Exception:
                        tmp = None

                # 2. Fall back to edge-tts with British voice
                if tmp is None:
                    import asyncio
                    import edge_tts

                    async def _synth():
                        tts = edge_tts.Communicate(text, "en-GB-RyanNeural",
                                                   rate="+5%")
                        fd, path = _tf.mkstemp(suffix=".mp3")
                        _os.close(fd)
                        await tts.save(path)
                        return path

                    loop = asyncio.new_event_loop()
                    try:
                        tmp = loop.run_until_complete(_synth())
                    finally:
                        loop.close()

                # 3. Play the mp3 (sounddevice → pygame)
                played = False
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
                    played = True
                except Exception:
                    pass

                if not played:
                    try:
                        import pygame
                        pygame.mixer.init()
                        pygame.mixer.music.load(tmp)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)
                        played = True
                    except Exception:
                        pass

                try:
                    _os.unlink(tmp)
                except Exception:
                    pass

                if not played:
                    raise RuntimeError("no audio backend")

            except Exception:
                try:
                    import pyttsx3
                    e = pyttsx3.init()
                    e.setProperty("rate", 185)
                    e.say(text)
                    e.runAndWait()
                except Exception:
                    pass
            finally:
                _ub.push("sphere_speaking", active=False)

        _tts_enqueue(_play)
```

- [ ] **Step 2: Also update the docstring on `speak()`**

Find (line ~3365):
```python
        """Speak text via edge-tts. Sentences are serialised through a single
        background queue so they never overlap. Falls back to pyttsx3."""
```

Replace with:
```python
        """Speak text via ElevenLabs (British JARVIS voice). Serialised through
        a single background queue. Falls back to en-GB-RyanNeural edge-tts,
        then pyttsx3."""
```

- [ ] **Step 3: Verify import is clean**

```bash
cd /Users/jakegoncalves/Jarvis && python3 -c "import main; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 4: Run all tests**

```bash
cd /Users/jakegoncalves/Jarvis && python3 -m pytest tests/ -v 2>&1 | tail -15
```

Expected: All 38 tests PASS.

---

## Task 4: Manual smoke test

- [ ] **Step 1: Ensure `requests` is installed**

```bash
python3 -c "import requests; print('requests ok')"
```

If it fails: `pip3 install requests`

- [ ] **Step 2: Test ElevenLabs directly**

```bash
cd /Users/jakegoncalves/Jarvis && python3 -c "
from config import get_elevenlabs_config
import requests, tempfile, os

cfg = get_elevenlabs_config()
print('Config:', cfg['voice_id'])

resp = requests.post(
    f'https://api.elevenlabs.io/v1/text-to-speech/{cfg[\"voice_id\"]}',
    headers={'xi-api-key': cfg['api_key'], 'Content-Type': 'application/json'},
    json={
        'text': 'Good morning. All systems are online.',
        'model_id': 'eleven_turbo_v2_5',
        'voice_settings': {'stability': 0.45, 'similarity_boost': 0.85, 'style': 0.35, 'use_speaker_boost': True}
    },
    timeout=10
)
print('Status:', resp.status_code)
if resp.status_code == 200:
    fd, tmp = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    open(tmp, 'wb').write(resp.content)
    print('Saved to:', tmp, '— play it to verify the voice')
else:
    print('Error:', resp.text[:200])
"
```

Expected: `Status: 200` and a temp mp3 path. Open the mp3 to hear the voice.

- [ ] **Step 3: Restart HUBERT and speak to it**

```bash
pkill -f "python.*main.py"; sleep 1; python3 main.py &
```

Say something to HUBERT and verify the response is spoken in the British JARVIS voice.

- [ ] **Step 4: Verify fallback still works**

Temporarily break the API key to test fallback:

```bash
cd /Users/jakegoncalves/Jarvis && python3 -c "
from config import load_config, save_config
cfg = load_config()
real_key = cfg['elevenlabs_api_key']
cfg['elevenlabs_api_key'] = 'sk_invalid'
save_config(cfg)
print('Key temporarily broken. Restart HUBERT and verify edge-tts British voice is used as fallback.')
print('Real key to restore:', real_key[:20], '...')
"
```

After verifying the fallback works, restore the real key:

```bash
cd /Users/jakegoncalves/Jarvis && python3 -c "
from config import set_elevenlabs_config
set_elevenlabs_config('sk_ad5c6e84975b3c40a85aa76e060290084f7f520b5514e87e')
print('Key restored.')
"
```

---

## Swapping to a Community JARVIS Voice

Once HUBERT is talking with the Daniel voice, if you want to use an actual JARVIS clone:

1. Go to elevenlabs.io/voice-library
2. Search "JARVIS" — pick a highly-rated one
3. Click "Add to voice library"
4. Copy the voice ID from its URL or the API response
5. Run:

```bash
cd /Users/jakegoncalves/Jarvis && python3 -c "
from config import set_elevenlabs_config
set_elevenlabs_config('sk_ad5c6e84975b3c40a85aa76e060290084f7f520b5514e87e', 'PASTE_VOICE_ID_HERE')
print('Voice updated.')
"
```

No code change needed — just the config.
