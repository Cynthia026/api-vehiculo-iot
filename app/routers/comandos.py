from fastapi import APIRouter, HTTPException, status
from typing import List
from app.schemas.comando import ComandoCreate, ComandoUpdate, ComandoResponse
from app.services.comando_service import comando_service

router = APIRouter(prefix="/api/comandos", tags=["Comandos"])

@router.get("/vehiculo/{id_vehiculo}", response_model=List[ComandoResponse])
def listar_comandos_vehiculo(id_vehiculo: int):
    return comando_service.obtener_comandos_vehiculo(id_vehiculo)

@router.post("/", status_code=status.HTTP_201_CREATED)
def crear_comando(comando: ComandoCreate):
    return comando_service.crear(comando)

@router.put("/{id_comando}")
def actualizar_comando(id_comando: int, comando: ComandoUpdate):
    comando_service.actualizar(id_comando, comando)
    return {"mensaje": "Comando actualizado"}

@router.delete("/{id_comando}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_comando(id_comando: int):
    comando_service.eliminar(id_comando)
    return None
