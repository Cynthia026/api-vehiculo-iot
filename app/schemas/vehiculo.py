from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class VehiculoBase(BaseModel):
    nombre: str = Field(..., max_length=50, description="Nombre o identificador del vehículo")
    descripcion: Optional[str] = Field(None, description="Descripción técnica o uso del dispositivo")
    activo: bool = Field(default=True, description="Estado operativo del vehículo")

class VehiculoCreate(VehiculoBase):
    pass

class VehiculoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=50)
    descripcion: Optional[str] = None
    activo: Optional[bool] = None

class VehiculoResponse(VehiculoBase):
    id_vehiculo: int
    # Hacemos las fechas opcionales por si la BD no las incluye o tienen otro nombre
    fecha_creacion: Optional[datetime] = None
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True