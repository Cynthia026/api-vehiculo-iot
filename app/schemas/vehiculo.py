from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class VehiculoBase(BaseModel):
    nombre: str = Field(..., max_length=80)
    modelo: str = Field(..., max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    microcontrolador: str = Field(..., max_length=50)

class VehiculoCreate(VehiculoBase):
    pass

class VehiculoUpdate(VehiculoBase):
    activo: bool

class VehiculoResponse(VehiculoBase):
    id_vehiculo: int
    activo: Optional[bool] = None

    class Config:
        from_attributes = True
