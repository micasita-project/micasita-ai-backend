"""La subida local debe ser recuperable por HTTP y nunca llamar a Cloudinary."""
from io import BytesIO
from unittest.mock import patch

from fastapi.staticfiles import StaticFiles
from PIL import Image

from app.core.config import settings


def photo():
    content = BytesIO()
    Image.new("RGB", (16, 16), "green").save(content, format="PNG")
    return content.getvalue()


def test_local_upload_can_be_downloaded_without_cloudinary(client, test_app, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_STORAGE", "local")
    monkeypatch.setattr(settings, "LOCAL_MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "LOCAL_MEDIA_BASE_URL", "")
    test_app.mount("/media", StaticFiles(directory=tmp_path), name="local-media")
    content = photo()
    with patch("cloudinary.uploader.upload") as remote:
        response = client.post("/properties/upload_image", files={"file": ("../../outside.png", content, "image/png")})
        assert response.status_code == 200
        url = response.json()["url"]
        assert url.startswith("http://testserver/media/") and url.endswith(".png")
        download = client.get(url)
        assert download.status_code == 200 and download.content == content
        assert download.headers["content-type"] == "image/png"
        assert len(list(tmp_path.iterdir())) == 1
        remote.assert_not_called()


def test_local_upload_uses_emulator_base_url(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_STORAGE", "local")
    monkeypatch.setattr(settings, "LOCAL_MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "LOCAL_MEDIA_BASE_URL", "http://10.0.2.2:8001/e2e-media")
    with patch("cloudinary.uploader.upload") as remote:
        response = client.post("/properties/upload_image", files={"file": ("fixture.png", photo(), "image/png")})
        assert response.status_code == 200
        assert response.json()["url"].startswith("http://10.0.2.2:8001/e2e-media/")
        remote.assert_not_called()


def test_cloudinary_mode_preserves_existing_upload(client, monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_STORAGE", "cloudinary")
    content = photo()
    with patch("cloudinary.uploader.upload", return_value={"secure_url": "https://example.test/photo.png"}) as remote:
        response = client.post("/properties/upload_image", files={"file": ("fixture.png", content, "image/png")})
        assert response.status_code == 200
        assert response.json()["url"] == "https://example.test/photo.png"
        remote.assert_called_once_with(content, resource_type="image", folder="micasita")


def test_invalid_local_image_is_rejected_without_writing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_STORAGE", "local")
    monkeypatch.setattr(settings, "LOCAL_MEDIA_DIR", str(tmp_path))
    with patch("cloudinary.uploader.upload") as remote:
        response = client.post("/properties/upload_image", files={"file": ("file.png", b"not an image", "image/png")})
        assert response.status_code == 400
        assert not list(tmp_path.iterdir())
        remote.assert_not_called()
