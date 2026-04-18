# File Upload Button — Design Spec
*2026-04-13*

## Goal

Add a 📎 file upload button to HUBERT's input bar so any file (image, STL, DWG, document, code, etc.) can be attached to a message. This is the foundation for the 3D design pipeline and any future file-aware tool.

---

## Architecture

A `📎` button sits in `InputBar.icons` below the mic button. Clicking it opens a native file picker (`tkinter.filedialog.askopenfilename`, no type filter). The selected path is stored in `InputBar._attached_file`.

The entry gets the filename injected as a prefix — `"📎 drawing.png — "` — cursor placed at the end so the user can type a description naturally. On send, `_fire()` reads both `self._attached_file` and the entry text (stripping the prefix), calls `_send(text, file_path=self._attached_file)`, then clears attachment state.

`_send()` detects file type by extension:
- **Image** (png, jpg, jpeg, gif, webp, pdf) → passes as `image_path` to the existing Claude vision path
- **Everything else** → appends `[File attached: filename.ext]` to the message text so Claude has context, stores the path in `self._last_file_path` for downstream tools (e.g. 3D pipeline)

---

## Components

### `InputBar` (modified)

| Addition | Detail |
|----------|--------|
| `self._attached_file = None` | Initialized in `__init__`, holds the pending file path |
| `self._attach_prefix = ""` | The injected text prefix, used to strip it on send |
| `📎` button in `icons` frame | Below `mic_btn`, same size (36×52), DIM color, calls `_pick_file()` |
| `_pick_file()` | Opens `filedialog.askopenfilename()`, stores path, injects `"📎 {name} — "` prefix into entry |
| `_clear_attachment()` | Clears `_attached_file`, removes prefix from entry text |
| `_fire()` update | Reads `_attached_file`, strips prefix from text, calls `_on_send(text, file_path)`, then calls `_clear_attachment()` |

### `App._send()` (modified)

| Addition | Detail |
|----------|--------|
| `file_path: str = None` kwarg | New optional parameter |
| Extension check | `Path(file_path).suffix.lower()` against image set |
| Image branch | Passes `file_path` as `image_path` to existing vision logic (no change to that path) |
| Non-image branch | Appends `\n[File attached: {name}]` to `text`; stores path in `self._last_file_path` |
| Chat bubble | Attachment note visible in user bubble so it's clear what was sent |

### `App._last_file_path` (new attribute)
Set in `_send()` when a non-image file is attached. The 3D pipeline (and any future tool) reads this to access the file. Cleared to `None` after each send.

---

## File Changes

| File | Change |
|------|--------|
| `main.py` | Modify `InputBar.__init__`, `InputBar._build`, `InputBar._fire` |
| `main.py` | Add `InputBar._pick_file`, `InputBar._clear_attachment` |
| `main.py` | Modify `App._send` signature and body |

No new files. No other files touched.

---

## Spec Self-Review

- **Placeholder scan:** No TBDs. All methods named and described.
- **Consistency:** `_attached_file` and `_attach_prefix` used consistently across all methods that touch them. `_last_file_path` set and cleared in `_send()`.
- **Scope:** Two methods added to `InputBar`, one kwarg + branch added to `_send()`. Appropriately bounded.
- **Ambiguity:** "Strip prefix from entry" — implementation strips exactly `self._attach_prefix` from the start of the entry text before sending.
