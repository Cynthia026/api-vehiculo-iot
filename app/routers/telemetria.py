from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.schemas.estado import EstadoVehiculoUpdate, EstadoVehiculoResponse
from app.schemas.historial import HistorialCreate, HistorialResponse
from app.services.telemetria_service import telemetria_service
from app.services.historial_service import historial_service
from app.websocket.manager import ws_manager
from app.security import get_current_user_optional, verificar_acceso_vehiculo, registrar_auditoria, COMANDOS_INVITADO
from app.database import db_manager

router = APIRouter(prefix="/api/telemetria", tags=["Telemetría y Estado"])

@router.get("/estado/{id_vehiculo}", response_model=EstadoVehiculoResponse)
def obtener_estado_vehiculo(
    id_vehiculo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    verificar_acceso_vehiculo(id_vehiculo, user, modo="lectura")
    estado = telemetria_service.obtener_estado(id_vehiculo)
    if not estado:
        raise HTTPException(status_code=404, detail="Estado no encontrado")
    return estado

@router.get("/historial/{id_vehiculo}", response_model=List[HistorialResponse])
def obtener_historial(
    id_vehiculo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    verificar_acceso_vehiculo(id_vehiculo, user, modo="lectura")
    historial_completo = historial_service.obtener_historial(id_vehiculo)
    if not historial_completo:
        return []
    return historial_completo[:10]

@router.post("/movimiento", response_model=EstadoVehiculoResponse)
async def ejecutar_movimiento_individual(
    id_vehiculo: int, 
    id_comando: int, 
    origen: str = "API_POST",
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    # 1. Autorización por recurso (RBAC + BOLA + Consentimiento Soporte + Reserva Invitado)
    verificar_acceso_vehiculo(id_vehiculo, user, modo="control")

    # 2. Verificar que el comando exista y esté habilitado para la unidad física
    cmds = db_manager.execute_query(
        "SELECT id_comando, nombre, activo FROM comandos WHERE id_comando = %s AND id_vehiculo = %s LIMIT 1",
        (id_comando, id_vehiculo)
    )
    if not cmds:
        raise HTTPException(
            status_code=422,
            detail=f"El comando {id_comando} no pertenece a la unidad #{id_vehiculo}."
        )
    if user and user.get("rol") == "INVITADO" and str(cmds[0].get("nombre", "")).strip().upper() not in COMANDOS_INVITADO:
        registrar_auditoria(
            user.get("id_usuario"), "INVITADO", "COMANDO_INVITADO_BLOQUEADO", "comandos", id_vehiculo,
            f"Invitado intentó usar '{cmds[0].get('nombre')}' en la unidad #{id_vehiculo}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"El comando '{cmds[0].get('nombre')}' no está disponible en la prueba de Invitado."
        )
    if cmds:
        if not cmds[0].get("activo"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"El comando '{cmds[0].get('nombre')}' no está habilitado para las capacidades de esta unidad."
            )
        # Prioridad absoluta de DETENER: si hay una DEMO activa en esta unidad, la cancela de inmediato
        if str(cmds[0].get("nombre", "")).strip().lower() == "detener":
            try:
                from app.routers.demos import active_demo_tasks
                if id_vehiculo in active_demo_tasks:
                    tarea = active_demo_tasks.pop(id_vehiculo)
                    tarea.cancel()
            except Exception:
                pass

    nuevo_historial = HistorialCreate(
        id_vehiculo=id_vehiculo, 
        id_comando=id_comando, 
        origen=origen
    )
    historial_service.registrar_movimiento(nuevo_historial)

    nuevo_estado = EstadoVehiculoUpdate(
        id_vehiculo=id_vehiculo,
        id_comando=id_comando,
        conectado=True
    )
    estado_actualizado = telemetria_service.actualizar_estado(nuevo_estado)

    if estado_actualizado:
        if "fecha_actualizacion" in estado_actualizado and isinstance(estado_actualizado["fecha_actualizacion"], datetime):
            estado_actualizado["fecha_actualizacion"] = estado_actualizado["fecha_actualizacion"].isoformat()
        
        payload = {
            "tipo_evento": "movimiento_individual",
            "vehiculo": id_vehiculo,
            "datos": estado_actualizado
        }
        await ws_manager.broadcast_json(payload)

    return estado_actualizado
