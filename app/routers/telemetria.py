from fastapi import APIRouter, HTTPException, BackgroundTasks, status
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
    """Obtiene la última telemetría conocida del vehículo."""
    estado = telemetria_service.obtener_estado(id_vehiculo)
    if not estado:
        raise HTTPException(status_code=404, detail="Estado no encontrado para el vehículo")
    return estado

@router.get("/historial/{id_vehiculo}", response_model=List[HistorialResponse])
def obtener_historial_vehiculo(id_vehiculo: int):
    """Obtiene los últimos 10 movimientos individuales (No incluye movimientos de DEMO)."""
    return historial_service.obtener_historial(id_vehiculo)

@router.delete("/historial/{id_vehiculo}", status_code=status.HTTP_204_NO_CONTENT)
def depurar_historial(id_vehiculo: int):
    """Limpia el registro histórico de un vehículo."""
    historial_service.limpiar_historial(id_vehiculo)
    return None

# --- FLUJO A: MOVIMIENTO INDIVIDUAL ---
@router.post("/movimiento", response_model=EstadoVehiculoResponse)
async def ejecutar_movimiento_individual(
    id_vehiculo: int, 
    id_comando: int, 
    velocidad: float, 
    orientacion: float
):
    """
    Ejecuta un movimiento individual: 
    1. Registra en el historial (sp_registrar_historial).
    2. Actualiza el estado (sp_actualizar_estado).
    3. Notifica por WebSocket.
    """
    # 1. Registrar el movimiento en la bitácora
    nuevo_historial = HistorialCreate(
        id_vehiculo=id_vehiculo, 
        id_comando=id_comando, 
        detalles=f"Movimiento manual a velocidad {velocidad}"
    )
    historial_service.registrar_movimiento(nuevo_historial)

    # 2. Actualizar el estado del vehículo en la BD
    nuevo_estado = EstadoVehiculoUpdate(
        id_vehiculo=id_vehiculo,
        estado="En Movimiento",
        velocidad=velocidad,
        bateria=98.5, # Simulación de sensor
        orientacion=orientacion,
        conexion_activa=True
    )
    estado_actualizado = telemetria_service.actualizar_estado(nuevo_estado)

    # 3. Notificar a los clientes conectados vía WebSocket
    if estado_actualizado:
        # Convertimos la fecha a string para poder enviarla por JSON
        if "ultima_actualizacion" in estado_actualizado and isinstance(estado_actualizado["ultima_actualizacion"], datetime):
            estado_actualizado["ultima_actualizacion"] = estado_actualizado["ultima_actualizacion"].isoformat()
            
        payload = {
            "tipo_evento": "movimiento_individual",
            "datos": estado_actualizado
        }
        await ws_manager.broadcast_json(payload)

    return estado_actualizado