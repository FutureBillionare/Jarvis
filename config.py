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
