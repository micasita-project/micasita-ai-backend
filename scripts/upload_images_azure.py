import os
import sys
import json
import uuid

# Agregamos la ruta principal al path para que pueda importar módulos de 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from azure.storage.blob import BlobServiceClient

def main():
    if not settings.AZURE_STORAGE_CONNECTION_STRING or not settings.AZURE_CONTAINER_NAME:
        print("Error: Configura AZURE_STORAGE_CONNECTION_STRING y AZURE_CONTAINER_NAME en tu .env")
        return

    # Iniciar cliente de Azure
    try:
        blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(settings.AZURE_CONTAINER_NAME)
    except Exception as e:
        print(f"Error inicializando Azure Blob Service: {e}")
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, "data", "raw", "housing.json")
    output_json_path = os.path.join(base_dir, "data", "raw", "housing_updated.json")
    images_base_dir = os.path.join(base_dir, "data", "images")

    if not os.path.exists(json_path):
        print(f"No se encontró el archivo {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        housing_data = json.load(f)

    # Diccionario para no subir la misma imagen dos veces si se repitiera la ruta
    uploaded_urls = {}

    total_properties = len(housing_data)
    
    for i, property in enumerate(housing_data):
        print(f"Procesando vivienda {i+1}/{total_properties} (ID: {property.get('id')})...")
        new_images = []
        for img_path in property.get('images', []):
            if img_path in uploaded_urls:
                new_images.append(uploaded_urls[img_path])
                continue

            # Extraer ruta relativa, ej: "3\foto_01.jpg"
            if "images\\" in img_path:
                rel_path = img_path.split("images\\")[-1]
            elif "images/" in img_path:
                rel_path = img_path.split("images/")[-1]
            else:
                # Si ya es un URL o tiene otro formato, lo dejamos igual
                if img_path.startswith("http"):
                    new_images.append(img_path)
                continue

            # Convertir separadores de Windows a OS actual
            rel_path = rel_path.replace("\\", "/")
            
            local_img_path = os.path.join(images_base_dir, rel_path)
            
            if os.path.exists(local_img_path):
                # Subir a Azure
                file_extension = rel_path.split(".")[-1] if "." in rel_path else "jpg"
                unique_filename = f"{uuid.uuid4()}.{file_extension}"
                
                try:
                    blob_client = container_client.get_blob_client(blob=unique_filename)
                    
                    # Set content type manually for common image extensions
                    # though azure storage SDK handles some guessing automatically.
                    with open(local_img_path, "rb") as data:
                        blob_client.upload_blob(data, overwrite=True)
                        
                    public_url = blob_client.url
                    uploaded_urls[img_path] = public_url
                    new_images.append(public_url)
                    print(f"  ✓ Subida {rel_path} -> {public_url}")
                except Exception as e:
                    print(f"  X Error subiendo {rel_path}: {e}")
                    new_images.append(img_path) # Dejar original si falla
            else:
                print(f"  - Archivo no encontrado localmente: {local_img_path}")
                new_images.append(img_path) # Dejar original si no existe
                
        # Reemplazar array de imágenes original
        property['images'] = new_images

    # Guardar nuevo JSON
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(housing_data, f, indent=2, ensure_ascii=False)
        
    print(f"\n¡Proceso finalizado! JSON guardado en: {output_json_path}")

if __name__ == "__main__":
    main()
