from pydantic import BaseModel, Field
from typing import Optional

class ComandoBase(BaseModel):
    id_vehiculo: int
    nombre: str = Field(..., max_length=60)
    codigo: int
    descripcion: Optional[str] = Field(None, max_length=255)

class ComandoCreate(ComandoBase):
    pass

class ComandoUpdate(BaseModel):
    nombre: str = Field(..., max_length=60)
    codigo: int
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: bool

class ComandoResponse(ComandoBase):
    id_comando: int
    activo: Optional[bool] = None

    class Config:
        from_attributes = True
