from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class Workplace(Base):
    __tablename__ = "workplaces"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    alias = Column(String, nullable=False) # Ej: "Oficina San Isidro", "Universidad Católica"
    work_lat = Column(Float, nullable=False)
    work_lon = Column(Float, nullable=False)
    budget = Column(Float, nullable=False)
    preferred_transportation = Column(String, nullable=False) # 'Auto', 'Bicicleta', 'Caminando'
    
    owner = relationship("User", back_populates="workplaces")
    recommendation_history = relationship("RecommendationHistory", back_populates="workplace", cascade="all, delete-orphan")

