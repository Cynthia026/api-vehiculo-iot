from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EstadoVehiculoUpdate(BaseModel):
    id_vehiculo: int
    id_comando: int
    conectado: bool

class EstadoVehiculoResponse(BaseModel):
    id_vehiculo: int
    vehiculo: str
    id_comando: int
    comando: Optional[str] = None
    codigo: Optional[int] = None
    conectado: bool
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True
