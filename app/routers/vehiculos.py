from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional, Dict, Any
from app.schemas.vehiculo import VehiculoCreate, VehiculoUpdate, VehiculoResponse
from app.services.vehiculo_service import vehiculo_service
from app.security import get_current_user_optional, require_roles, verificar_acceso_vehiculo, ids_unidades_visibles, registrar_auditoria
from app.database import db_manager

router = APIRouter(prefix="/api/vehiculos", tags=["Vehículos"])

@router.get("/", response_model=List[VehiculoResponse])
def listar_vehiculos(user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):
    """Consulta los vehículos visibles para quien pregunta (ADMIN: todos; USUARIO: los suyos; sin sesión/Invitado: exhibición)."""
    todos = vehiculo_service.obtener_todos()
    visibles = ids_unidades_visibles(user)
    if visibles is None:
        return todos
    return [v for v in todos if int(v.get("id_vehiculo", 0)) in visibles]

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
    """
    Baja LÓGICA de una unidad (Solo ADMIN): se marca activo = 0 y estado INACTIVO.
    Nunca se borra la fila para conservar historial, demos y auditoría.
    """
    filas = db_manager.execute_query(
        """
        SELECT v.id_vehiculo, a.id_usuario AS id_propietario
        FROM vehiculos v
        LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
        WHERE v.id_vehiculo = %s LIMIT 1
        """,
        (id_vehiculo,)
    )
    if not filas:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    if filas[0].get("id_propietario"):
        raise HTTPException(status_code=409, detail="La unidad tiene un comprador asignado: revoca la asignación antes de darla de baja.")
    db_manager.execute_write(
        "UPDATE vehiculos SET activo = 0, estado_comercial = 'INACTIVO' WHERE id_vehiculo = %s",
        (id_vehiculo,)
    )
    registrar_auditoria(user["id_usuario"], "ADMIN", "BAJA_LOGICA_UNIDAD", "vehiculos", id_vehiculo,
                        f"Unidad #{id_vehiculo} dada de baja (activo = 0, estado INACTIVO)")
    return None
