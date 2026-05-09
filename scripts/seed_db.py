import json
import os
import sys

# Agregamos la ruta principal al path para que pueda importar módulos de 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.core.security import get_password_hash
from app.models.user import User
from app.models.workplace import Workplace
from app.models.property import Property
from app.models.recommendation_history import RecommendationHistory
from app.models.recommendation_preference import RecommendationPreference

JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "housing_updated.json")

def seed_database():
    print("Iniciando proceso de seeding...")
    
    # 1. Asegurar que las tablas existan (sin borrarlas)
    print("Verificando las tablas de la base de datos...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Verificar si ya existe data
        if db.query(User).first() is not None:
            print("Ya existen datos en la base de datos. Omitiendo proceso de seeding...")
            return

        # 2. Crear usuario por defecto
        print("Creando usuario por defecto (admin@micasita.ai)...")
        default_user = User(
            email="admin@micasita.ai",
            hashed_password=get_password_hash("password123"),
            role="admin",
            home_lat=-11.895428501274143,
            home_lon=-77.04029923406615, 
            home_address="Hermenegildo rojas 125",
            is_active=True
        )
        db.add(default_user)
        db.commit()
        db.refresh(default_user)
        
        # 3. Crear lugar de trabajo por defecto
        print("Creando lugar de trabajo asociado...")
        workplace = Workplace(
            user_id=default_user.id,
            work_address="Oficina Central",
            work_lat=-12.0931, # San Isidro
            work_lon=-77.0465
        )
        db.add(workplace)
        db.commit()
        db.refresh(workplace)
        
        # 3.1 Crear preferencias de recomendacion para el workplace
        pref = RecommendationPreference(
            user_id=default_user.id,
            workplace_id=workplace.id,
            budget=1500.0,
            preferred_transportation="driving",
            max_distance_km=10.0
        )
        db.add(pref)
        db.commit()
        
        # 4. Cargar el JSON e insertar las propiedades en lotes
        print(f"Cargando dataset desde {JSON_PATH}...")
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            properties_data = json.load(f)
            
        print(f"Se encontraron {len(properties_data)} propiedades en el archivo.")
        
        batch_size = 1000
        batch = []
        total_inserted = 0
        
        for item in properties_data:
            # Filtrar casas sin precio o con precio 0
            price = item.get("price")
            if price is None or float(price) == 0.0:
                continue
                
            # Validaciones básicas por los Not Null Constraints
            total_area = item.get("total_area_sqm")
            if total_area is None:
                total_area = item.get("covered_area_sqm", 0.0) or 0.0
                
            property_obj = Property(
                publisher_id=default_user.id,
                title=item.get("title") or "Sin Título",
                property_type=item.get("property_type") or "Desconocido",
                district=item.get("district") or "Desconocido",
                address=item.get("address") or "Sin Dirección",
                latitude=item.get("latitude") or 0.0,
                longitude=item.get("longitude") or 0.0,
                currency=item.get("currency"),
                price=item.get("price"),
                total_area_sqm=total_area,
                covered_area_sqm=item.get("covered_area_sqm"),
                bedrooms=item.get("bedrooms"),
                bathrooms=item.get("bathrooms"),
                parking=item.get("parking"),
                antiquity=item.get("antiquity"),
                description=item.get("description"),
                images=item.get("images") or [],
                source_url=item.get("source_url"),
                features=item.get("features") or [],
                status="approved", # Las casas del seed se marcan como aprobadas automáticamente
                rejection_reason=None
            )
            
            batch.append(property_obj)
            
            if len(batch) >= batch_size:
                db.add_all(batch)
                db.commit()
                total_inserted += len(batch)
                batch = []
                print(f"Insertados {total_inserted}/{len(properties_data)}...")
                
        # Insertar los restantes
        if batch:
            db.add_all(batch)
            db.commit()
            total_inserted += len(batch)
            print(f"Insertados {total_inserted}/{len(properties_data)}...")
            
        print("¡Proceso de seeding completado exitosamente!")
            
    except Exception as e:
        db.rollback()
        print(f"Error durante el seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
