from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional, Dict, Any
from app.schemas.comando import ComandoCreate, ComandoUpdate, ComandoResponse
from app.services.comando_service import comando_service
from app.security import get_current_user_optional, require_roles, verificar_acceso_vehiculo

router = APIRouter(prefix="/api/comandos", tags=["Comandos"])

@router.get("/vehiculo/{id_vehiculo}", response_model=List[ComandoResponse])
def listar_comandos_vehiculo(
    id_vehiculo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    verificar_acceso_vehiculo(id_vehiculo, user, modo="lectura")
    return comando_service.obtener_comandos_vehiculo(id_vehiculo)

@router.post("/", status_code=status.HTTP_201_CREATED)
def crear_comando(
    comando: ComandoCreate,
    user: Dict[str, Any] = Depends(require_roles("ADMIN"))
):
    return comando_service.crear(comando)

@router.put("/{id_comando}")
def actualizar_comando(
    id_comando: int,
    comando: ComandoUpdate,
    user: Dict[str, Any] = Depends(require_roles("ADMIN"))
):
    comando_service.actualizar(id_comando, comando)
    return {"mensaje": "Comando actualizado"}

@router.delete("/{id_comando}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_comando(
    id_comando: int,
    user: Dict[str, Any] = Depends(require_roles("ADMIN"))
):
    comando_service.eliminar(id_comando)
    return None
