"""Tests for file upload routing logic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from file_upload_utils import classify_file, build_attachment_note

IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
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

    def test_pdf_is_file(self):
        assert classify_file("/tmp/doc.pdf") == "file"

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
