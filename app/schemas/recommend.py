from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.schemas.property import PropertyResponse

class GuestRecommendRequest(BaseModel):
    work_lat: float
    work_lon: float
    budget: float
    preferred_transportation: str # 'Auto', 'Bicicleta', 'Caminando'

class RecommendationResponse(BaseModel):
    property: PropertyResponse
    match_score: float # Puntaje del 0 al 100 de XGBoost
    predicted_time_min: float # Tiempo simulado al trabajo

class RecommendationHistoryResponse(BaseModel):
    id: int
    workplace_id: int
    results: List[RecommendationResponse]
    created_at: datetime

    class Config:
        from_attributes = True

