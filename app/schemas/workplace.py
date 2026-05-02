from pydantic import BaseModel

class WorkplaceBase(BaseModel):
    work_address: str
    work_lat: float
    work_lon: float

class WorkplaceCreate(WorkplaceBase):
    pass

class WorkplaceUpdate(BaseModel):
    work_address: str | None = None
    work_lat: float | None = None
    work_lon: float | None = None

class WorkplaceResponse(WorkplaceBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
