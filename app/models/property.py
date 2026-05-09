from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from app.core.database import Base

class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    publisher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    title = Column(String, nullable=False)
    property_type = Column(String, nullable=False)
    district = Column(String, nullable=False)
    address = Column(String, nullable=False)
    
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    currency = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    total_area_sqm = Column(Float, nullable=False)
    covered_area_sqm = Column(Float, nullable=True)
    
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    parking = Column(Integer, nullable=True)
    antiquity = Column(Integer, nullable=True)
    
    description = Column(Text, nullable=True)
    
    # ARRAY es nativo de PostgreSQL, brillante para guardar listas de URLs de Cloudinary
    images = Column(ARRAY(String), default=[]) 
    source_url = Column(String, nullable=True)
    
    # Moderación
    status = Column(String, default="pending") # 'pending', 'approved', 'rejected'
    rejection_reason = Column(String, nullable=True)

    # Amenidades y características extra
    features = Column(ARRAY(String), default=[])
