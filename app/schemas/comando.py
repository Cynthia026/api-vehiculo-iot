from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ComandoBase(BaseModel):
    id_vehiculo: int = Field(..., description="ID del vehículo al que pertenece el comando")
    nombre_comando: str = Field(..., max_length=50, description="Ej. 'Avanzar', 'Girar_Izq'")
    instruccion_hex: str = Field(..., max_length=20, description="Código hexadecimal para el ESP32/ESP8266")
    activo: bool = Field(default=True)

class ComandoCreate(ComandoBase):
    pass

class ComandoUpdate(BaseModel):
    nombre_comando: Optional[str] = Field(None, max_length=50)
    instruccion_hex: Optional[str] = Field(None, max_length=20)
    activo: Optional[bool] = None

# ... resto del código superior de comando.py ...

class ComandoResponse(ComandoBase):
    id_comando: int
    fecha_creacion: Optional[datetime] = None

    class Config:
        from_attributes = True