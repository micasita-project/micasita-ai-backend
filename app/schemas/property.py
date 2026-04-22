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
    source_url: Optional[str] = None

class PropertyCreate(PropertyBase):
    pass

class PropertyResponse(PropertyBase):
    id: int
    publisher_id: int

    class Config:
        from_attributes = True

# Respuesta al subir una imagen a Cloudinary en solitario
class ImageUploadResponse(BaseModel):
    url: str
