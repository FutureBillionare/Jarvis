"""Tests for ElevenLabs config helpers in config.py."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config import _DEFAULT_EL_VOICE as DEFAULT_VOICE_ID


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
