from sqlalchemy import Column, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime


class RecommendationHistory(Base):
    __tablename__ = "recommendation_history"

    id = Column(Integer, primary_key=True, index=True)
    workplace_id = Column(Integer, ForeignKey("workplaces.id", ondelete="CASCADE"), nullable=False)

    # Resultados de XGBoost serializados como JSON string
    results = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    workplace = relationship("Workplace", back_populates="recommendation_history")
