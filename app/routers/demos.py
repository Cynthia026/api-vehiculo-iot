import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, status
from typing import List
from app.schemas.demo import DemoCreate, DemoResponse, MovimientoDemoCreate, MovimientoDemoResponse
from app.services.demo_service import demo_service
from app.services.telemetria_service import telemetria_service
from app.schemas.estado import EstadoVehiculoUpdate
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/api/demos", tags=["Secuencias DEMO"])

# --- ENDPOINT WEBSOCKET ---
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Canal de comunicación bidireccional para monitoreo en tiempo real."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Mantenemos la conexión viva esperando mensajes (ping/pong)
            data = await websocket.receive_text()
            # Opcional: responder si el cliente manda algo
            # await websocket.send_text(f"Servidor recibió: {data}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        print("[WebSocket] Cliente desconectado.")

# --- CATÁLOGO DE DEMOS ---
@router.get("/", response_model=List[DemoResponse])
def listar_demos():
    return demo_service.obtener_demos()

@router.get("/{id_demo}", response_model=DemoResponse)
def obtener_demo(id_demo: int):
    demo = demo_service.obtener_demo_id(id_demo)
    if not demo:
        raise HTTPException(status_code=404, detail="Demo no encontrada")
    return demo

@router.post("/", response_model=DemoResponse, status_code=status.HTTP_201_CREATED)
def crear_demo(demo: DemoCreate):
    return demo_service.crear_demo(demo)

@router.delete("/{id_demo}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_demo(id_demo: int):
    if not demo_service.eliminar_demo(id_demo):
        raise HTTPException(status_code=404, detail="Demo no encontrada")
    return None

@router.post("/{id_demo}/movimientos", status_code=status.HTTP_201_CREATED)
def agregar_movimiento_demo(id_demo: int, mov: MovimientoDemoCreate):
    if mov.id_demo != id_demo:
        raise HTTPException(status_code=400, detail="El ID de la ruta y el cuerpo no coinciden")
    demo_service.agregar_movimiento(mov)
    return {"mensaje": "Movimiento agregado a la secuencia demo"}

@router.get("/{id_demo}/movimientos")
def obtener_movimientos_demo(id_demo: int):
    return demo_service.obtener_movimientos(id_demo)

# --- FLUJO B: EJECUCIÓN ASÍNCRONA DE DEMO ---
async def tarea_ejecutar_demo(id_demo: int, id_vehiculo: int):
    """
    Regla de Negocio: Ejecuta N movimientos temporizados transmitiendo por WebSocket.
    CRÍTICO: NO ejecuta sp_registrar_historial en ningún momento.
    """
    movimientos = demo_service.obtener_movimientos(id_demo)
    if not movimientos:
        return

    print(f"\n[DEMO] Iniciando secuencia Demo {id_demo} para el Vehículo {id_vehiculo}...")
    
    for mov in movimientos:
        # Extraer tiempos
        duracion_segundos = mov.get('duracion_ms', 1000) / 1000.0
        pausa_segundos = mov.get('pausa_ms', 500) / 1000.0
        
        # Enviar estado actual al WebSocket
        payload = {
            "tipo_evento": "movimiento_demo",
            "vehiculo": id_vehiculo,
            "comando_en_ejecucion": mov.get('id_comando'),
            "accion": "ejecutando_paso",
            "orden": mov.get('orden')
        }
        await ws_manager.broadcast_json(payload)
        
        # Esperar la duración de la instrucción
        await asyncio.sleep(duracion_segundos)
        
        # Pausa antes del siguiente movimiento
        await asyncio.sleep(pausa_segundos)

    # Al finalizar, actualizar el estado final del vehículo a 'Detenido'
    estado_final = EstadoVehiculoUpdate(
        id_vehiculo=id_vehiculo,
        estado="Detenido (Fin de Demo)",
        velocidad=0.0,
        bateria=95.0,
        orientacion=0.0,
        conexion_activa=True
    )
    telemetria_service.actualizar_estado(estado_final)
    
    # Notificar fin de demo
    await ws_manager.broadcast_json({"tipo_evento": "fin_demo", "vehiculo": id_vehiculo})
    print(f"[DEMO] Secuencia {id_demo} finalizada.")

@router.post("/{id_demo}/ejecutar")
async def iniciar_ejecucion_demo(id_demo: int, id_vehiculo: int, background_tasks: BackgroundTasks):
    """
    Inicia una rutina DEMO. Devuelve respuesta HTTP inmediata mientras 
    la rutina corre asíncronamente en segundo plano.
    """
    demo = demo_service.obtener_demo_id(id_demo)
    if not demo:
        raise HTTPException(status_code=404, detail="Demo no encontrada")
    
    # Delegar la ejecución iterativa a una tarea en segundo plano
    background_tasks.add_task(tarea_ejecutar_demo, id_demo, id_vehiculo)
    
    return {"mensaje": "Secuencia DEMO iniciada", "vehiculo": id_vehiculo, "demo": demo.get("nombre_demo")}