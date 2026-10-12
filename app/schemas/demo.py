from pydantic import BaseModel, Field
from typing import Optional

class DemoBase(BaseModel):
    nombre_demo: str = Field(..., max_length=50)
    descripcion: Optional[str] = None
    activo: bool = True

class DemoCreate(DemoBase):
    pass

class DemoResponse(DemoBase):
    id_demo: int

    class Config:
        from_attributes = True

class MovimientoDemoCreate(BaseModel):
    id_demo: int
    id_comando: int
    orden: int
    duracion_ms: int
    pausa_ms: int

class MovimientoDemoResponse(MovimientoDemoCreate):
    id_movimiento: int

    class Config:
        from_attributes = True