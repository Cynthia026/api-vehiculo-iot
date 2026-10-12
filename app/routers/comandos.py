from fastapi import APIRouter, HTTPException, status
from typing import List
from app.schemas.comando import ComandoCreate, ComandoUpdate, ComandoResponse
from app.services.comando_service import comando_service

router = APIRouter(prefix="/api/comandos", tags=["Comandos"])

@router.get("/", response_model=List[ComandoResponse])
def listar_comandos():
    """Consulta todos los comandos registrados."""
    return comando_service.obtener_todos()

@router.get("/{id_comando}", response_model=ComandoResponse)
def obtener_comando(id_comando: int):
    """Consulta un comando específico por su ID."""
    comando = comando_service.obtener_por_id(id_comando)
    if not comando:
        raise HTTPException(status_code=404, detail="Comando no encontrado")
    return comando

@router.post("/", response_model=ComandoResponse, status_code=status.HTTP_201_CREATED)
def crear_comando(comando: ComandoCreate):
    """Crea una nueva instrucción para un vehículo."""
    return comando_service.crear(comando)

@router.put("/{id_comando}", response_model=ComandoResponse)
def actualizar_comando(id_comando: int, comando: ComandoUpdate):
    """Modifica una instrucción existente."""
    actualizado = comando_service.actualizar(id_comando, comando)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Comando no encontrado")
    return actualizado

@router.delete("/{id_comando}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_comando(id_comando: int):
    """Elimina un comando del sistema."""
    if not comando_service.eliminar(id_comando):
        raise HTTPException(status_code=404, detail="Comando no encontrado")
    return None