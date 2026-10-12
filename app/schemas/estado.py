from pydantic import BaseModel, Field
from datetime import datetime

class EstadoVehiculoUpdate(BaseModel):
    id_vehiculo: int
    estado: str = Field(..., max_length=20, description="Ej. 'En Movimiento', 'Detenido'")
    velocidad: float
    bateria: float
    orientacion: float
    conexion_activa: bool

class EstadoVehiculoResponse(EstadoVehiculoUpdate):
    id_estado: int
    ultima_actualizacion: datetime

    class Config:
        from_attributes = True