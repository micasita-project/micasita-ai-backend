"""Almacenamiento de imágenes nuevas; la BD conserva únicamente sus URLs."""
from pathlib import Path
from uuid import uuid4
from io import BytesIO

import cloudinary.uploader
from fastapi import Request
from PIL import Image

from app.core.config import settings


def save_property_image(content: bytes, request: Request) -> str:
    if settings.IMAGE_STORAGE == "local":
        directory = Path(settings.LOCAL_MEDIA_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        # El nombre no depende del nombre de archivo enviado por el cliente.
        with Image.open(BytesIO(content)) as image:
            extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}.get(image.format)
            if not extension:
                raise ValueError("Formato de imagen no admitido para almacenamiento local")
            image.verify()
        name = f"{uuid4().hex}.{extension}"
        (directory / name).write_bytes(content)
        if settings.LOCAL_MEDIA_BASE_URL:
            return f"{settings.LOCAL_MEDIA_BASE_URL.rstrip('/')}/{name}"
        return str(request.url_for("local-media", path=name))

    result = cloudinary.uploader.upload(content, resource_type="image", folder="micasita")
    return result["secure_url"]
