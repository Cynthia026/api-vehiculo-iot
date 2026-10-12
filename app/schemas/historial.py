from pydantic import BaseModel, Field
from datetime import datetime

class HistorialCreate(BaseModel):
    id_vehiculo: int
    id_comando: int
    detalles: str = Field(default="", max_length=255)

class HistorialResponse(HistorialCreate):
    id_historial: int
    fecha_ejecucion: datetime

    class Config:
        from_attributes = True