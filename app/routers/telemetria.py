from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime
from app.schemas.estado import EstadoVehiculoUpdate, EstadoVehiculoResponse
from app.schemas.historial import HistorialCreate, HistorialResponse
from app.services.telemetria_service import telemetria_service
from app.services.historial_service import historial_service
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/api/telemetria", tags=["Telemetría y Estado"])

@router.get("/estado/{id_vehiculo}", response_model=EstadoVehiculoResponse)
def obtener_estado_vehiculo(id_vehiculo: int):
    estado = telemetria_service.obtener_estado(id_vehiculo)
    if not estado:
        raise HTTPException(status_code=404, detail="Estado no encontrado")
    return estado

@router.get("/historial/{id_vehiculo}", response_model=List[HistorialResponse])
def obtener_historial(id_vehiculo: int):
    # Obtienes la lista completa del servicio
    historial_completo = telemetria_service.obtener_historial(id_vehiculo)
    
    # Devuelves solo los primeros 10 elementos
    return historial_completo[:10]

@router.post("/movimiento", response_model=EstadoVehiculoResponse)
async def ejecutar_movimiento_individual(
    id_vehiculo: int, 
    id_comando: int, 
    origen: str = "API_POST"
):
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
            "datos": estado_actualizado
        }
        await ws_manager.broadcast_json(payload)

    return estado_actualizado
