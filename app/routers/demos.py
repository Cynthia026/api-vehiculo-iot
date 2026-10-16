import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, status
from typing import List
from app.schemas.demo import DemoCreate, DemoUpdate, DemoResponse, MovimientoDemoCreate, MovimientoDemoUpdate, MovimientoDemoResponse
from app.services.demo_service import demo_service
from app.services.telemetria_service import telemetria_service
from app.schemas.estado import EstadoVehiculoUpdate
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/api/demos", tags=["Secuencias DEMO"])

@router.websocket("/ws/{id_vehiculo}")
async def websocket_endpoint(websocket: WebSocket, id_vehiculo: int):
    # Le pasamos el ID al manager
    await ws_manager.connect(websocket, id_vehiculo)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        # Lo desconectamos de ese ID
        ws_manager.disconnect(websocket, id_vehiculo)

@router.get("/vehiculo/{id_vehiculo}", response_model=List[DemoResponse])
def listar_demos_vehiculo(id_vehiculo: int):
    return demo_service.obtener_demos(id_vehiculo)

@router.post("/", status_code=status.HTTP_201_CREATED)
def crear_demo(demo: DemoCreate):
    return demo_service.crear_demo(demo)

@router.put("/{id_demo}")
def actualizar_demo(id_demo: int, demo: DemoUpdate):
    demo_service.actualizar_demo(id_demo, demo)
    return {"mensaje": "Demo actualizada"}

@router.delete("/{id_demo}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_demo(id_demo: int):
    demo_service.eliminar_demo(id_demo)
    return None

@router.post("/{id_demo}/movimientos", status_code=status.HTTP_201_CREATED)
def agregar_movimiento_demo(id_demo: int, mov: MovimientoDemoCreate):
    if mov.id_demo != id_demo:
        raise HTTPException(status_code=400, detail="El ID no coincide")
    demo_service.agregar_movimiento(mov)
    return {"mensaje": "Movimiento agregado"}

@router.get("/{id_demo}/movimientos", response_model=List[MovimientoDemoResponse])
def obtener_movimientos_demo(id_demo: int):
    return demo_service.obtener_movimientos(id_demo)

@router.put("/movimientos/{id_demo_movimiento}")
def actualizar_movimiento_demo(id_demo_movimiento: int, mov: MovimientoDemoUpdate):
    demo_service.actualizar_movimiento(id_demo_movimiento, mov)
    return {"mensaje": "Movimiento actualizado"}

@router.delete("/movimientos/{id_demo_movimiento}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_movimiento_demo(id_demo_movimiento: int):
    demo_service.eliminar_movimiento(id_demo_movimiento)
    return None

async def tarea_ejecutar_demo(id_demo: int, id_vehiculo: int):
    movimientos = demo_service.obtener_movimientos(id_demo)
    if not movimientos:
        return
    
    # 1. Notificar inicio (Opcional, pero muy recomendado)
    await ws_manager.broadcast_json({"tipo_evento": "inicio_demo", "vehiculo": id_vehiculo})
    
    for mov in movimientos:
        duracion_segundos = mov.get('duracion_ms', 1000) / 1000.0
        pausa_segundos = mov.get('pausa_ms', 500) / 1000.0
        id_cmd_actual = mov.get('id_comando')
        
        # --- CORRECCIÓN: ACTUALIZAR ESTADO EN BD DURANTE EL PASO ---
        estado_actual = EstadoVehiculoUpdate(
            id_vehiculo=id_vehiculo,
            id_comando=id_cmd_actual, # Ponemos el comando que se está ejecutando
            conectado=True
        )
        telemetria_service.actualizar_estado(estado_actual) # Llama al SP de estado en RDS
        # -----------------------------------------------------------

        payload = {
            "tipo_evento": "movimiento_demo",
            "vehiculo": id_vehiculo,
            "comando_en_ejecucion": id_cmd_actual,
            "accion": "ejecutando_paso",
            "orden": mov.get('orden')
        }
        
        await ws_manager.broadcast_json(payload)
        await asyncio.sleep(duracion_segundos)
        await asyncio.sleep(pausa_segundos)

    # 2. Notificar Fin y restablecer estado a 0 (Detenido/Standby)
    estado_final = EstadoVehiculoUpdate(
        id_vehiculo=id_vehiculo,
        id_comando=0,
        conectado=True
    )
    telemetria_service.actualizar_estado(estado_final)
    await ws_manager.broadcast_json({"tipo_evento": "fin_demo", "vehiculo": id_vehiculo})

@router.post("/{id_demo}/ejecutar")
async def iniciar_ejecucion_demo(id_demo: int, id_vehiculo: int, background_tasks: BackgroundTasks):
    background_tasks.add_task(tarea_ejecutar_demo, id_demo, id_vehiculo)
    return {"mensaje": "Secuencia DEMO iniciada", "vehiculo": id_vehiculo, "demo": id_demo}
