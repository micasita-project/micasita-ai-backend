from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.schemas.property import PropertyResponse

class GuestRecommendRequest(BaseModel):
    work_lat: float
    work_lon: float
    budget: float
    preferred_transportation: str  # 'driving', 'cycling', 'walking'
    max_distance_km: Optional[float] = 10.0
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None

class RecommendationResponse(BaseModel):
    property: PropertyResponse
    match_score: float  # Puntaje del 0 al 100 de XGBoost
    predicted_time_min: float  # Tiempo simulado al trabajo en minutos
    time_saved_mins: Optional[float] = None  # Tiempo ahorrado vs casa actual

class RecommendationPageResponse(BaseModel):
    results: List[RecommendationResponse]
    total: int
    message: Optional[str] = None  # Explica por qué no hay resultados
    min_price_in_area: Optional[float] = None  # Precio mínimo disponible en el radio elegido

class RecommendationHistoryResponse(BaseModel):
    id: int
    workplace_id: int
    results: List[RecommendationResponse]
    created_at: datetime

    class Config:
        from_attributes = True

