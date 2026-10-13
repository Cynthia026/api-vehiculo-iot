from pydantic import BaseModel, Field
from typing import Optional

class DemoBase(BaseModel):
    id_vehiculo: int
    nombre: str = Field(..., max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)

class DemoCreate(DemoBase):
    pass

class DemoUpdate(BaseModel):
    nombre: str = Field(..., max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: bool

class DemoResponse(DemoBase):
    id_demo: int
    activo: Optional[bool] = None

    class Config:
        from_attributes = True

class MovimientoDemoCreate(BaseModel):
    id_demo: int
    id_comando: int
    orden: int
    duracion_ms: int
    pausa_ms: int

class MovimientoDemoUpdate(BaseModel):
    id_comando: int
    orden: int
    duracion_ms: int
    pausa_ms: int

class MovimientoDemoResponse(MovimientoDemoCreate):
    id_demo_movimiento: int
    comando: Optional[str] = None
    codigo: Optional[int] = None

    class Config:
        from_attributes = True
