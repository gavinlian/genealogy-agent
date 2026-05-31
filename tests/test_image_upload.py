import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from image_upload import decode_image_bytes, normalize_image_base64, save_upload_image


def test_normalize_data_url():
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    raw = f"data:image/png;base64,{png}"
    data = decode_image_bytes(raw)
    assert data.startswith(b"\x89PNG")


def test_save_upload_image(tmp_path):
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    name, data = save_upload_image(str(tmp_path), png)
    assert name.endswith(".png")
    assert os.path.isfile(os.path.join(tmp_path, name))


def test_invalid_base64():
    with pytest.raises(ValueError):
        decode_image_bytes("not-valid!!!")
