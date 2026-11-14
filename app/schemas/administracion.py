from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=120)
    password: str = Field(..., min_length=4, max_length=100)


class GuestSessionRequest(BaseModel):
    nombre_visitante: Optional[str] = Field("Visitante Showroom", max_length=80)
    id_vehiculo: Optional[int] = None


class ModeloCatalogoCreate(BaseModel):
    codigo_modelo: str = Field(..., max_length=40)
    nombre: str = Field(..., max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    microcontrolador_default: str = Field("ESP8266", max_length=50)
    tiene_brazo: bool = True
    tiene_motores_giro: bool = True


class UnidadAdminCreate(BaseModel):
    nombre: str = Field(..., max_length=80)
    id_modelo: Optional[int] = 1
    modelo: Optional[str] = Field("Excavadora IoT", max_length=80)
    numero_serie: str = Field(..., max_length=60)
    descripcion: Optional[str] = Field(None, max_length=255)
    microcontrolador: str = Field("ESP8266", max_length=50)
    estado_comercial: str = Field("DISPONIBLE", max_length=30)


class UnidadAdminUpdate(BaseModel):
    nombre: str = Field(..., max_length=80)
    modelo: str = Field(..., max_length=80)
    numero_serie: Optional[str] = Field(None, max_length=60)
    descripcion: Optional[str] = Field(None, max_length=255)
    microcontrolador: str = Field("ESP8266", max_length=50)
    estado_comercial: str = Field("DISPONIBLE", max_length=30)
    activo: bool = True


class ClienteCreate(BaseModel):
    nombre: str = Field(..., max_length=100)
    email: str = Field(..., max_length=120)
    password: str = Field(..., min_length=6, max_length=100)


class AsignacionCreate(BaseModel):
    id_vehiculo: int
    id_usuario: int
    notas: Optional[str] = Field(None, max_length=255)


class SoporteToggleRequest(BaseModel):
    autorizado: bool
    minutos: int = Field(30, ge=5, le=240)
