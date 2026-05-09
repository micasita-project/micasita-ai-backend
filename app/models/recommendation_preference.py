from sqlalchemy import Column, Integer, String, Float, ForeignKey
from app.core.database import Base

class RecommendationPreference(Base):
    __tablename__ = "recommendation_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workplace_id = Column(Integer, ForeignKey("workplaces.id", ondelete="CASCADE"), nullable=False)
    
    budget = Column(Float, nullable=False)
    preferred_transportation = Column(String, nullable=False) # 'driving', 'cycling', 'walking'
    max_distance_km = Column(Float, nullable=True, default=10.0)
