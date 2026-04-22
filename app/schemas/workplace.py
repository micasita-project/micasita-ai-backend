from pydantic import BaseModel

class WorkplaceBase(BaseModel):
    alias: str
    work_lat: float
    work_lon: float
    budget: float
    preferred_transportation: str

class WorkplaceCreate(WorkplaceBase):
    pass

class WorkplaceResponse(WorkplaceBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
