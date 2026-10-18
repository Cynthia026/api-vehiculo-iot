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
# Guarda las tareas activas para evitar simultaneidad y permitir cancelación
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
    """Tarea asíncrona de fondo que ejecuta la secuencia de movimientos."""
    try:
        movimientos = demo_service.obtener_movimientos(id_demo)
        if not movimientos:
            return
        
        await ws_manager.broadcast_json({"tipo_evento": "inicio_demo", "vehiculo": id_vehiculo})
        
        for mov in movimientos:
            duracion_segundos = mov.get('duracion_ms', 1000) / 1000.0
            pausa_segundos = mov.get('pausa_ms', 500) / 1000.0
            id_cmd_actual = mov.get('id_comando')
            
            # Actualizamos la BD en cada paso
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
            # El ciclo duerme, permitiendo que la tarea sea cancelada
            await asyncio.sleep(duracion_segundos)
            await asyncio.sleep(pausa_segundos)

        # Si termina normal, notificamos fin y restauramos BD
        estado_final = EstadoVehiculoUpdate(id_vehiculo=id_vehiculo, id_comando=9, conectado=True)
        telemetria_service.actualizar_estado(estado_final)
        await ws_manager.broadcast_json({"tipo_evento": "fin_demo", "vehiculo": id_vehiculo})

    except asyncio.CancelledError:
        # CORRECCIÓN CRÍTICA: En lugar de usar "raise", pasamos en silencio.
        # Esto permite que la tarea muera en paz sin generar conflictos ni errores 500.
        pass

    finally:
        # Limpieza de seguridad: quitar la tarea del diccionario al terminar (si aún existe)
        if id_vehiculo in active_demo_tasks:
            del active_demo_tasks[id_vehiculo]


@router.post("/{id_demo}/ejecutar")
async def iniciar_ejecucion_demo(id_demo: int, id_vehiculo: int):
    """Punto 9 de Rúbrica: Inicia la demo y bloquea ejecuciones simultáneas."""
    if id_vehiculo in active_demo_tasks:
        raise HTTPException(
            status_code=400, 
            detail=f"El vehículo {id_vehiculo} ya está ejecutando una DEMO. Cancele la actual o espere."
        )

    tarea = asyncio.create_task(tarea_ejecutar_demo(id_demo, id_vehiculo))
    active_demo_tasks[id_vehiculo] = tarea

    return {"mensaje": "Secuencia DEMO iniciada", "vehiculo": id_vehiculo, "demo": id_demo}


@router.post("/vehiculo/{id_vehiculo}/cancelar")
async def cancelar_ejecucion_demo(id_vehiculo: int):
    """Punto 9 de Rúbrica: Detiene la ejecución si hay una DEMO en curso."""
    try:
        if id_vehiculo not in active_demo_tasks:
            return {"mensaje": "No hay ninguna DEMO en curso para este vehículo."}
        
        # 1. CORRECCIÓN CRÍTICA: Usamos .pop() para sacar la tarea del diccionario
        # de forma segura antes de matarla. Esto evita "carreras" entre procesos.
        tarea_activa = active_demo_tasks.pop(id_vehiculo)
        tarea_activa.cancel()
        
        # 2. Restauramos la BD para que quede en Standby (comando 0)
        estado_cancelado = EstadoVehiculoUpdate(id_vehiculo=id_vehiculo, id_comando=9, conectado=True)
        telemetria_service.actualizar_estado(estado_cancelado)
        
        # 3. Avisamos por WebSocket de manera garantizada
        await ws_manager.broadcast_json({"tipo_evento": "cancelacion_demo", "vehiculo": id_vehiculo})
        
        return {"mensaje": f"Se ha enviado la señal de detención al vehículo {id_vehiculo}."}
    
    except Exception as e:
        # Si algo extraordinario pasa (ej. BD desconectada), en vez de un 500 ciego,
        # arrojamos el texto exacto del error para saber qué corregir.
        raise HTTPException(status_code=500, detail=f"Error interno al cancelar: {str(e)}")