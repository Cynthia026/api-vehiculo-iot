from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class HistorialCreate(BaseModel):
    id_vehiculo: int
    id_comando: int
    origen: str = Field(..., max_length=30)

class HistorialResponse(BaseModel):
    id_historial: int
    id_vehiculo: int
    comando: Optional[str] = None
    codigo: Optional[int] = None
    fecha_hora: Optional[datetime] = None
    origen: str

    class Config:
        from_attributes = True
