from pydantic import BaseModel
from typing import List, Optional

class PropertyBase(BaseModel):
    title: str
    property_type: str
    district: str
    address: str
    latitude: float
    longitude: float
    currency: Optional[str] = None
    price: Optional[float] = None
    total_area_sqm: float
    covered_area_sqm: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[int] = None
    antiquity: Optional[int] = None
    description: Optional[str] = None
    images: List[str] = []
    features: List[str] = []
    source_url: Optional[str] = None

class PropertyCreate(PropertyBase):
    pass

class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    property_type: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    currency: Optional[str] = None
    price: Optional[float] = None
    total_area_sqm: Optional[float] = None
    covered_area_sqm: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[int] = None
    antiquity: Optional[int] = None
    description: Optional[str] = None
    images: Optional[List[str]] = None
    features: Optional[List[str]] = None
    source_url: Optional[str] = None

class PropertyStatusUpdate(BaseModel):
    status: str # 'approved' or 'rejected'

class PropertyResponse(PropertyBase):
    id: int
    publisher_id: int
    status: str

    class Config:
        from_attributes = True

# Respuesta al subir una imagen a Cloudinary en solitario
class ImageUploadResponse(BaseModel):
    url: str
