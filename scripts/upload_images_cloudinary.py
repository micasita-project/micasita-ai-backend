import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageOps, UnidentifiedImageError
import cloudinary
import cloudinary.uploader
from app.core.config import settings
import json
from io import BytesIO

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)

JPEG_QUALITY = 92
WEBP_QUALITY = 92


def compress_image(local_img_path):
    with Image.open(local_img_path) as image:
        image = ImageOps.exif_transpose(image)
        image_format = (image.format or os.path.splitext(local_img_path)[1].lstrip(".")).upper()
        output = BytesIO()

        if image_format in {"JPG", "JPEG"}:
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            return output.getvalue()

        if image_format == "PNG":
            if image.mode not in {"RGB", "RGBA", "L", "LA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            image.save(output, format="PNG", optimize=True, compress_level=9)
            return output.getvalue()

        if image_format == "WEBP":
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            image.save(output, format="WEBP", quality=WEBP_QUALITY, method=6)
            return output.getvalue()

        if image.mode not in {"RGB", "RGBA", "L", "LA"}:
            image = image.convert("RGB")
        image.save(output, format=image_format)
        return output.getvalue()


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, "data", "raw", "housing.json")
    output_json_path = os.path.join(base_dir, "data", "raw", "housing_updated.json")
    images_base_dir = os.path.join(base_dir, "data", "raw", "images")

    if not os.path.exists(json_path):
        print(f"No se encontró el archivo {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        housing_data = json.load(f)

    uploaded_urls = {}
    total_properties = len(housing_data)

    for i, property in enumerate(housing_data):
        print(f"Procesando vivienda {i+1}/{total_properties} (ID: {property.get('id')})...")
        new_images = []

        for img_path in property.get("images", []):
            # Si ya fue subida antes en esta misma ejecución, reutilizar URL
            if img_path in uploaded_urls:
                new_images.append(uploaded_urls[img_path])
                continue

            # Si ya es una URL externa, dejarla tal cual
            if img_path.startswith("http"):
                new_images.append(img_path)
                continue

            # Extraer ruta relativa desde "images/" o "images\"
            if "images\\" in img_path:
                rel_path = img_path.split("images\\")[-1]
            elif "images/" in img_path:
                rel_path = img_path.split("images/")[-1]
            else:
                new_images.append(img_path)
                continue

            rel_path = rel_path.replace("\\", "/")
            local_img_path = os.path.join(images_base_dir, rel_path)

            if not os.path.exists(local_img_path):
                print(f"  - Archivo no encontrado: {local_img_path}")
                new_images.append(img_path)
                continue

            try:
                compressed = compress_image(local_img_path)
            except UnidentifiedImageError:
                print(f"  X Imagen inválida: {local_img_path}")
                new_images.append(img_path)
                continue

            try:
                result = cloudinary.uploader.upload(
                    compressed,
                    resource_type="image",
                    folder="micasita",
                )
                public_url = result["secure_url"]
                uploaded_urls[img_path] = public_url
                new_images.append(public_url)
                print(f"  ✓ {rel_path} -> {public_url}")
            except Exception as e:
                print(f"  X Error subiendo {rel_path}: {e}")
                new_images.append(img_path)

        property["images"] = new_images

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(housing_data, f, indent=2, ensure_ascii=False)

    print(f"\n¡Proceso finalizado! JSON actualizado en: {output_json_path}")


if __name__ == "__main__":
    main()
