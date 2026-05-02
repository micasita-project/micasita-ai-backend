from pydantic import BaseModel, Field
from typing import Optional

class RecommendationPreferenceBase(BaseModel):
    workplace_id: int
    budget: float
    preferred_transportation: str
    max_distance_km: float = Field(default=10.0, ge=1.0, le=50.0)

class RecommendationPreferenceCreate(RecommendationPreferenceBase):
    pass

class RecommendationPreferenceUpdate(BaseModel):
    budget: Optional[float] = None
    preferred_transportation: Optional[str] = None
    max_distance_km: Optional[float] = Field(default=None, ge=1.0, le=50.0)

class RecommendationPreferenceResponse(RecommendationPreferenceBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
