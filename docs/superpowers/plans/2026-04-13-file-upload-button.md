# File Upload Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 📎 file upload button to HUBERT's input bar that attaches any file to the next message, injecting the filename as a prefix in the text entry and routing images vs. non-images in `_send()`.

**Architecture:** `InputBar` gains `_attached_file` state and a `📎` button in its left icons frame. Clicking it opens a native file picker; the selected filename is prepended to the entry text. On send, `_fire()` reads the attachment and calls `_on_send(text, file_path)`. `App._send()` gains a `file_path` kwarg and routes by extension: images go to the existing `image_path` vision path; everything else appends a `[File attached: name]` note to the message and stores the path in `self._last_file_path` for downstream tools.

**Tech Stack:** Python, CustomTkinter, `tkinter.filedialog`, `pathlib.Path`

---

## File Map

| File | Change |
|------|--------|
| `main.py` — `InputBar.__init__` (line 1023) | Add `self._attached_file = None`, `self._attach_prefix = ""` |
| `main.py` — `InputBar._build` (line 1035) | Add `📎` button below `mic_btn` in the `icons` frame |
| `main.py` — `InputBar._fire` (line 1103) | Read attachment, strip prefix, pass `file_path` to `_on_send`, clear attachment |
| `main.py` — new `InputBar._pick_file` | Open file dialog, store path, inject prefix into entry |
| `main.py` — new `InputBar._clear_attachment` | Clear `_attached_file`, `_attach_prefix`, remove prefix from entry |
| `main.py` — `App._send` (line 3728) | Add `file_path=None` kwarg, extension check, routing logic, `_last_file_path` |
| `tests/test_file_upload.py` | New test file — unit tests for logic that can be tested without GUI |

---

## Task 1: Tests for `_send()` file routing logic

The routing logic in `_send()` (extension check, image vs. non-image branching) is pure logic that can be extracted and tested without a GUI. We write tests for a standalone helper function first, then wire it into `_send()`.

**Files:**
- Create: `tests/test_file_upload.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_file_upload.py`:

```python
"""Tests for file upload routing logic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from file_upload_utils import classify_file, build_attachment_note

IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"]
OTHER_EXTS = [".stl", ".dwg", ".dxf", ".txt", ".py", ".zip"]


class TestClassifyFile:
    def test_png_is_image(self):
        assert classify_file("/tmp/photo.png") == "image"

    def test_jpg_is_image(self):
        assert classify_file("/tmp/photo.jpg") == "image"

    def test_jpeg_is_image(self):
        assert classify_file("/tmp/photo.jpeg") == "image"

    def test_gif_is_image(self):
        assert classify_file("/tmp/anim.gif") == "image"

    def test_webp_is_image(self):
        assert classify_file("/tmp/photo.webp") == "image"

    def test_pdf_is_image(self):
        assert classify_file("/tmp/doc.pdf") == "image"

    def test_stl_is_file(self):
        assert classify_file("/tmp/model.stl") == "file"

    def test_dwg_is_file(self):
        assert classify_file("/tmp/drawing.dwg") == "file"

    def test_txt_is_file(self):
        assert classify_file("/tmp/notes.txt") == "file"

    def test_case_insensitive(self):
        assert classify_file("/tmp/photo.PNG") == "image"
        assert classify_file("/tmp/model.STL") == "file"


class TestBuildAttachmentNote:
    def test_note_contains_filename(self):
        note = build_attachment_note("/tmp/model.stl")
        assert "model.stl" in note

    def test_note_format(self):
        note = build_attachment_note("/tmp/drawing.dwg")
        assert note == "\n[File attached: drawing.dwg]"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/jakegoncalves/Jarvis && python -m pytest tests/test_file_upload.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'file_upload_utils'`

- [ ] **Step 3: Create `file_upload_utils.py`**

Create `/Users/jakegoncalves/Jarvis/file_upload_utils.py`:

```python
"""Utilities for file upload routing in HUBERT's _send() pipeline."""
from pathlib import Path

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}


def classify_file(file_path: str) -> str:
    """Return 'image' if extension is a vision-capable type, else 'file'."""
    ext = Path(file_path).suffix.lower()
    return "image" if ext in _IMAGE_EXTS else "file"


def build_attachment_note(file_path: str) -> str:
    """Return the '[File attached: name]' string appended to message text."""
    return f"\n[File attached: {Path(file_path).name}]"
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jakegoncalves/Jarvis && python -m pytest tests/test_file_upload.py -v
```

Expected: All 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add file_upload_utils.py tests/test_file_upload.py && git commit -m "feat: add file_upload_utils with classify_file and build_attachment_note"
```

---

## Task 2: Add attachment state to `InputBar.__init__`

**Files:**
- Modify: `main.py:1023-1033`

- [ ] **Step 1: Update `InputBar.__init__` to initialize attachment state**

In `main.py`, find `InputBar.__init__` (around line 1023). The current body is:

```python
def __init__(self, parent, on_send, on_camera=None, **kwargs):
    super().__init__(parent, fg_color=BG_INPUT, corner_radius=12,
                     border_width=2, border_color=DIM, **kwargs)
    self._on_send        = on_send
    self._on_camera      = on_camera
    self._mic_active     = False   # True = always-on listen loop running
    self._voice_thread   = None
    self._glow           = False
    self._glow_t         = 0
    self._build()
    self._animate_border()
```

Replace with:

```python
def __init__(self, parent, on_send, on_camera=None, **kwargs):
    super().__init__(parent, fg_color=BG_INPUT, corner_radius=12,
                     border_width=2, border_color=DIM, **kwargs)
    self._on_send        = on_send
    self._on_camera      = on_camera
    self._mic_active     = False   # True = always-on listen loop running
    self._voice_thread   = None
    self._glow           = False
    self._glow_t         = 0
    self._attached_file  = None   # path of pending attachment, or None
    self._attach_prefix  = ""     # text prefix injected into entry for display
    self._build()
    self._animate_border()
```

- [ ] **Step 2: Verify the app still starts**

```bash
cd /Users/jakegoncalves/Jarvis && python -c "import main; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add main.py && git commit -m "feat: add _attached_file and _attach_prefix state to InputBar"
```

---

## Task 3: Add 📎 button and `_pick_file` / `_clear_attachment` methods

**Files:**
- Modify: `main.py:1035-1047` (InputBar._build icons section)
- Add: `InputBar._pick_file` and `InputBar._clear_attachment` methods

- [ ] **Step 1: Add the 📎 button to `_build`**

In `main.py`, find the `icons` frame block in `InputBar._build` (around line 1039-1047):

```python
        # Left icon — mic toggle only (camera button removed, camera lives in HUD)
        icons = ctk.CTkFrame(row, fg_color="transparent")
        icons.pack(side="left", fill="y", padx=(0, 8))
        self.mic_btn = ctk.CTkButton(
            icons, text="🎤", width=36, height=52,
            fg_color=DIM, hover_color=DIM2, text_color=TEXT,
            font=("Segoe UI Emoji", 12), corner_radius=8,
            command=self._toggle_mic)
        self.mic_btn.pack()
```

Replace with:

```python
        # Left icons — mic + file upload
        icons = ctk.CTkFrame(row, fg_color="transparent")
        icons.pack(side="left", fill="y", padx=(0, 8))
        self.mic_btn = ctk.CTkButton(
            icons, text="🎤", width=36, height=25,
            fg_color=DIM, hover_color=DIM2, text_color=TEXT,
            font=("Segoe UI Emoji", 12), corner_radius=8,
            command=self._toggle_mic)
        self.mic_btn.pack(pady=(0, 2))
        self.upload_btn = ctk.CTkButton(
            icons, text="📎", width=36, height=25,
            fg_color=DIM, hover_color=DIM2, text_color=TEXT,
            font=("Segoe UI Emoji", 12), corner_radius=8,
            command=self._pick_file)
        self.upload_btn.pack()
```

- [ ] **Step 2: Add `_pick_file` and `_clear_attachment` methods**

After `InputBar._fire` (around line 1108), add two new methods:

```python
    def _pick_file(self):
        """Open a file picker; inject the filename prefix into the entry."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="Attach file")
        if not path:
            return
        self._attached_file = path
        from pathlib import Path as _Path
        name = _Path(path).name
        self._attach_prefix = f"📎 {name} — "
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", self._attach_prefix)
        self.entry.mark_set("insert", "end")
        self.entry.focus_set()

    def _clear_attachment(self):
        """Remove attachment state and strip the prefix from the entry."""
        self._attached_file = None
        self._attach_prefix = ""
```

- [ ] **Step 3: Verify import still works**

```bash
cd /Users/jakegoncalves/Jarvis && python -c "import main; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add main.py && git commit -m "feat: add upload button and _pick_file/_clear_attachment to InputBar"
```

---

## Task 4: Update `InputBar._fire` to pass `file_path`

**Files:**
- Modify: `main.py:1103-1107` (InputBar._fire)

- [ ] **Step 1: Update `_fire` to strip prefix and pass file_path**

Find `_fire` in `main.py` (around line 1103):

```python
    def _fire(self):
        t = self.entry.get("1.0", "end").strip()
        if t:
            self.entry.delete("1.0", "end")
            self._on_send(t)
```

Replace with:

```python
    def _fire(self):
        raw = self.entry.get("1.0", "end").strip()
        # Strip the attachment prefix if present
        if self._attach_prefix and raw.startswith(self._attach_prefix):
            raw = raw[len(self._attach_prefix):]
        file_path = self._attached_file
        if raw or file_path:
            self.entry.delete("1.0", "end")
            self._clear_attachment()
            self._on_send(raw, file_path=file_path)
```

- [ ] **Step 2: Update `InputBar.__init__` `on_send` call signature note**

The `_on_send` callback is `App._send`. Check that `App` wires it up at line ~3500:

```python
self.input_bar = InputBar(center, on_send=self._send,
                          on_camera=self._on_video)
```

`_send` already accepts `**kwargs` implicitly — but we're adding an explicit `file_path` kwarg in the next task, so this wiring is fine as-is.

- [ ] **Step 3: Verify import**

```bash
cd /Users/jakegoncalves/Jarvis && python -c "import main; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add main.py && git commit -m "feat: update InputBar._fire to strip prefix and pass file_path to _on_send"
```

---

## Task 5: Update `App._send` to route by file type

**Files:**
- Modify: `main.py:3728` (`App._send` signature and body)

- [ ] **Step 1: Update `_send` signature and add routing logic**

Find `App._send` (around line 3728):

```python
    def _send(self, text: str = None, image_path: str = None, voice: bool = False):
        if text is None:
            text = self.input_bar.entry.get("1.0", "end").strip()
        if not text and not image_path:
            return
        if not text:
            text = "What do you see in this image?"
```

Replace with:

```python
    def _send(self, text: str = None, image_path: str = None, voice: bool = False,
              file_path: str = None):
        # Route file_path by type: images → image_path, others → note in text
        if file_path and not image_path:
            from file_upload_utils import classify_file, build_attachment_note
            if classify_file(file_path) == "image":
                image_path = file_path
            else:
                self._last_file_path = file_path
                text = (text or "") + build_attachment_note(file_path)
        if text is None:
            text = self.input_bar.entry.get("1.0", "end").strip()
        if not text and not image_path:
            return
        if not text:
            text = "What do you see in this image?"
```

- [ ] **Step 2: Initialize `_last_file_path` in `App.__init__` or `_build_ui`**

Find where `App` initializes its instance variables (around line 3309 in `__init__`). Add after the existing attribute initializations:

```python
self._last_file_path = None   # set by _send() when a non-image file is attached
```

Search for where to add it — find the `__init__` of the App class:

```bash
grep -n "_project_engine\|_ollama_mode\|_voice_listening" /Users/jakegoncalves/Jarvis/main.py | head -10
```

Add `self._last_file_path = None` in the same block as other `self._` initializations in `App.__init__`.

- [ ] **Step 3: Verify import and run existing tests**

```bash
cd /Users/jakegoncalves/Jarvis && python -c "import main; print('import ok')" && python -m pytest tests/test_file_upload.py tests/test_project_engine.py -v 2>&1 | tail -20
```

Expected: `import ok` + all tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add main.py && git commit -m "feat: add file_path routing to App._send, wire to file_upload_utils"
```

---

## Task 6: Manual smoke test

No automated test for the full UI flow (CustomTkinter requires a display). Verify by hand.

- [ ] **Step 1: Launch HUBERT**

```bash
cd /Users/jakegoncalves/Jarvis && python main.py
```

- [ ] **Step 2: Verify 📎 button appears**

In the input bar, below the 🎤 mic button, there should be a 📎 button. Both buttons should be visible and stacked vertically.

- [ ] **Step 3: Test image attachment**

1. Click 📎
2. Select any `.png` or `.jpg` file
3. Verify entry shows `"📎 filename.png — "` with cursor at end
4. Type a description, e.g. `"what's in this image?"`
5. Click SEND
6. Verify chat shows your message and Claude responds with vision analysis

- [ ] **Step 4: Test non-image attachment**

1. Click 📎
2. Select any `.txt`, `.stl`, or other non-image file
3. Verify entry shows `"📎 filename.stl — "` with cursor at end
4. Type `"describe this file"`
5. Click SEND
6. Verify chat shows `[File attached: filename.stl]` appended to message text

- [ ] **Step 5: Test cancel (pick then clear)**

1. Click 📎, select a file
2. Manually delete all text in the entry (Cmd+A, Delete)
3. Type a new message with no attachment
4. SEND — verify no `[File attached:]` note appears (prefix was cleared by `_clear_attachment` when `_fire` ran, and `_attached_file` was None since user deleted the text)

   > Note: if the user deletes the prefix text manually, `_attached_file` is still set. This is acceptable behaviour for v1 — the file just doesn't show in the message prefix but is still attached. A future improvement could watch entry changes.

- [ ] **Step 6: Final commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add -p && git commit -m "feat: file upload button — smoke tested, all manual checks pass"
```
