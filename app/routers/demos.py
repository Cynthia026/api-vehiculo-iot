import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, status
from typing import List, Dict
from app.schemas.demo import DemoCreate, DemoUpdate, DemoResponse, MovimientoDemoCreate, MovimientoDemoUpdate, MovimientoDemoResponse
from app.services.demo_service import demo_service
from app.services.telemetria_service import telemetria_service
from app.schemas.estado import EstadoVehiculoUpdate
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/api/demos", tags=["Secuencias DEMO"])

# --- DICCIONARIO GLOBAL DE TAREAS EN CURSO ---
# Guarda las tareas activas: { id_vehiculo: Task_De_Asyncio }
active_demo_tasks: Dict[int, asyncio.Task] = {}

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
    try:
        movimientos = demo_service.obtener_movimientos(id_demo)
        if not movimientos:
            return
        
        await ws_manager.broadcast_json({"tipo_evento": "inicio_demo", "vehiculo": id_vehiculo})
        
        for mov in movimientos:
            duracion_segundos = mov.get('duracion_ms', 1000) / 1000.0
            pausa_segundos = mov.get('pausa_ms', 500) / 1000.0
            id_cmd_actual = mov.get('id_comando')
            
            estado_actual = EstadoVehiculoUpdate(
                id_vehiculo=id_vehiculo,
                id_comando=id_cmd_actual,
                conectado=True
            )
            telemetria_service.actualizar_estado(estado_actual) 

            payload = {
                "tipo_evento": "movimiento_demo",
                "vehiculo": id_vehiculo,
                "comando_en_ejecucion": id_cmd_actual,
                "accion": "ejecutando_paso",
                "orden": mov.get('orden')
            }
            
            await ws_manager.broadcast_json(payload)
            # El ciclo duerme, aquí es donde asyncio inyecta la CancelledError si apretamos el botón de Stop
            await asyncio.sleep(duracion_segundos)
            await asyncio.sleep(pausa_segundos)

        # Si termina normal, notificamos fin normal y limpiamos la tarea activa
        estado_final = EstadoVehiculoUpdate(id_vehiculo=id_vehiculo, id_comando=0, conectado=True)
        telemetria_service.actualizar_estado(estado_final)
        await ws_manager.broadcast_json({"tipo_evento": "fin_demo", "vehiculo": id_vehiculo})

    except asyncio.CancelledError:
        # --- LÓGICA DE CANCELACIÓN DE EMERGENCIA ---
        print(f"[DEMO] Tarea cancelada para el vehiculo {id_vehiculo}")
        estado_cancelado = EstadoVehiculoUpdate(id_vehiculo=id_vehiculo, id_comando=0, conectado=True)
        telemetria_service.actualizar_estado(estado_cancelado)
        await ws_manager.broadcast_json({"tipo_evento": "cancelacion_demo", "vehiculo": id_vehiculo})
        # Levantamos el error de nuevo para que Asyncio sepa que sí la matamos correctamente
        raise

    finally:
        # Siempre quitamos la tarea del diccionario cuando termina (sea normal o cancelada)
        if id_vehiculo in active_demo_tasks:
            del active_demo_tasks[id_vehiculo]


@router.post("/{id_demo}/ejecutar")
async def iniciar_ejecucion_demo(id_demo: int, id_vehiculo: int):
    # 1. EVITAR SIMULTANEIDAD: Si ya hay una tarea viva para este vehículo, lanzamos error
    if id_vehiculo in active_demo_tasks:
        raise HTTPException(
            status_code=400, 
            detail=f"El vehículo {id_vehiculo} ya está ejecutando una DEMO. Cancele la actual o espere."
        )

    # 2. INICIAR Y GUARDAR TAREA: Usamos create_task para tener control total de la vida del proceso
    tarea = asyncio.create_task(tarea_ejecutar_demo(id_demo, id_vehiculo))
    active_demo_tasks[id_vehiculo] = tarea

    return {"mensaje": "Secuencia DEMO iniciada", "vehiculo": id_vehiculo, "demo": id_demo}


@router.post("/vehiculo/{id_vehiculo}/cancelar")
async def cancelar_ejecucion_demo(id_vehiculo: int):
    """Punto 9 de Rúbrica: Detiene la ejecución si hay una DEMO en curso."""
    if id_vehiculo not in active_demo_tasks:
        return {"mensaje": "No hay ninguna DEMO en curso para este vehículo."}
    
    # Extraer la tarea del diccionario y cancelarla "a la mala"
    tarea_activa = active_demo_tasks[id_vehiculo]
    tarea_activa.cancel()
    
    return {"mensaje": f"Se ha enviado la señal de detención al vehículo {id_vehiculo}."}