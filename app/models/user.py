from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user") # 'admin' o 'user'
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=True)  # True for existing users; new registrations start False
    
    name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    
    # Ubicación de casa actual (se completa en el onboarding)
    home_lat = Column(Float, nullable=True)
    home_lon = Column(Float, nullable=True)
    home_address = Column(String, nullable=True)
    
    # Consentimiento a la política de privacidad (Ley N.° 29733)
    consent_accepted_at = Column(DateTime, nullable=True)
    consent_version = Column(String(20), nullable=True)

    workplaces = relationship("Workplace", back_populates="owner", cascade="all, delete-orphan")
