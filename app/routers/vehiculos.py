from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional, Dict, Any
from app.schemas.vehiculo import VehiculoCreate, VehiculoUpdate, VehiculoResponse
from app.services.vehiculo_service import vehiculo_service
from app.security import get_current_user_optional, require_roles, verificar_acceso_vehiculo

router = APIRouter(prefix="/api/vehiculos", tags=["Vehículos"])

@router.get("/", response_model=List[VehiculoResponse])
def listar_vehiculos(user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    """Consulta los vehículos registrados."""
    return vehiculo_service.obtener_todos()

@router.get("/{id_vehiculo}", response_model=VehiculoResponse)
def obtener_vehiculo(
    id_vehiculo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    """Consulta un vehículo específico por su ID validando permisos."""
    verificar_acceso_vehiculo(id_vehiculo, user, modo="lectura")
    vehiculo = vehiculo_service.obtener_por_id(id_vehiculo)
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return vehiculo

@router.post("/", response_model=VehiculoResponse, status_code=status.HTTP_201_CREATED)
def crear_vehiculo(
    vehiculo: VehiculoCreate,
    user: Dict[str, Any] = Depends(require_roles("ADMIN"))
):
    """Registra un nuevo vehículo en la base de datos (Solo ADMIN)."""
    return vehiculo_service.crear(vehiculo)

@router.put("/{id_vehiculo}", response_model=VehiculoResponse)
def actualizar_vehiculo(
    id_vehiculo: int,
    vehiculo: VehiculoUpdate,
    user: Dict[str, Any] = Depends(require_roles("ADMIN"))
):
    """Actualiza los datos de un vehículo existente (Solo ADMIN)."""
    actualizado = vehiculo_service.actualizar(id_vehiculo, vehiculo)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return actualizado

@router.delete("/{id_vehiculo}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_vehiculo(
    id_vehiculo: int,
    user: Dict[str, Any] = Depends(require_roles("ADMIN"))
):
    """Elimina (o desactiva) un vehículo del sistema (Solo ADMIN)."""
    if not vehiculo_service.eliminar(id_vehiculo):
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return None
