import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, status
from typing import List, Dict, Optional, Any
from app.schemas.demo import DemoCreate, DemoUpdate, DemoResponse, MovimientoDemoCreate, MovimientoDemoUpdate, MovimientoDemoResponse
from app.services.demo_service import demo_service
from app.services.telemetria_service import telemetria_service
from app.schemas.estado import EstadoVehiculoUpdate
from app.websocket.manager import ws_manager
from app.security import (
    get_current_user_optional,
    decode_access_token,
    verificar_acceso_vehiculo,
    registrar_auditoria
)
from app.database import db_manager

router = APIRouter(prefix="/api/demos", tags=["Secuencias DEMO"])

# --- DICCIONARIO GLOBAL DE TAREAS EN CURSO ---
# Guarda las tareas activas para evitar simultaneidad y permitir cancelación
active_demo_tasks: Dict[int, asyncio.Task] = {}


def _obtener_id_comando_detener(id_vehiculo: int) -> int:
    """Resuelve dinámicamente el id_comando de 'Detener' para el vehículo indicado."""
    try:
        filas = db_manager.execute_query(
            "SELECT id_comando FROM comandos WHERE id_vehiculo = %s AND LOWER(nombre) = 'detener' LIMIT 1",
            (id_vehiculo,)
        )
        if filas:
            return int(filas[0]["id_comando"])
    except Exception:
        pass
    return 12


@router.websocket("/ws/{id_vehiculo}")
async def websocket_endpoint(websocket: WebSocket, id_vehiculo: int):
    # Si el cliente envía ?token=..., validamos su autorización sobre la unidad antes de aceptar
    token = websocket.query_params.get("token")
    if token:
        try:
            user = decode_access_token(token)
            verificar_acceso_vehiculo(id_vehiculo, user, modo="lectura")
        except HTTPException:
            await websocket.close(code=4003)
            return

    await ws_manager.connect(websocket, id_vehiculo)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, id_vehiculo)


@router.get("/vehiculo/{id_vehiculo}")
def listar_demos_vehiculo(
    id_vehiculo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    verificar_acceso_vehiculo(id_vehiculo, user, modo="lectura")
    demos = demo_service.obtener_demos(id_vehiculo)

    # Enriquecer con tipo_demo e id_usuario_creador si las columnas existen en RDS
    try:
        meta = db_manager.execute_query(
            """
            SELECT d.id_demo,
                   COALESCE(d.tipo_demo, 'EMPRESA') AS tipo_demo,
                   d.id_usuario_creador,
                   COALESCE(d.duracion_max_seg, 60) AS duracion_max_seg,
                   u.nombre AS nombre_creador
            FROM demos d
            LEFT JOIN usuarios u ON u.id_usuario = d.id_usuario_creador
            WHERE d.id_vehiculo = %s
            """,
            (id_vehiculo,)
        )
        mapa_meta = {m["id_demo"]: m for m in meta}
        resultado = []
        for d in demos:
            info = mapa_meta.get(d["id_demo"], {})
            item = {
                **d,
                "tipo_demo": info.get("tipo_demo", "EMPRESA"),
                "id_usuario_creador": info.get("id_usuario_creador"),
                "duracion_max_seg": info.get("duracion_max_seg", 60),
                "nombre_creador": info.get("nombre_creador") or "Empresa IoT"
            }
            # Si es un USUARIO comprador, ve demos de EMPRESA y sus propias demos PRIVADAS
            if user and user.get("rol") == "USUARIO":
                if item["tipo_demo"] == "PRIVADA" and item["id_usuario_creador"] not in (None, user.get("id_usuario")):
                    continue
            resultado.append(item)
        return resultado
    except Exception:
        return demos


@router.post("/", status_code=status.HTTP_201_CREATED)
def crear_demo(
    demo: DemoCreate,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    if user and user.get("rol") == "INVITADO":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El perfil Invitado no puede crear nuevas demos.")

    verificar_acceso_vehiculo(demo.id_vehiculo, user, modo="control" if (user and user.get("rol") == "USUARIO") else "lectura")
    creada = demo_service.crear_demo(demo)

    # Etiquetar si fue creada por ADMIN (EMPRESA) o por USUARIO comprador (PRIVADA)
    if creada and creada.get("id_demo") and user:
        tipo = "EMPRESA" if user.get("rol") == "ADMIN" else "PRIVADA"
        try:
            db_manager.execute_write(
                "UPDATE demos SET id_usuario_creador = %s, tipo_demo = %s WHERE id_demo = %s",
                (user.get("id_usuario"), tipo, creada["id_demo"])
            )
            creada["tipo_demo"] = tipo
            creada["id_usuario_creador"] = user.get("id_usuario")
        except Exception:
            pass
        registrar_auditoria(
            user.get("id_usuario"), user.get("rol", "USUARIO"), "CREAR_DEMO", "demos",
            creada["id_demo"], f"Demo '{demo.nombre}' ({tipo}) creada para unidad #{demo.id_vehiculo}"
        )

    return creada


@router.put("/{id_demo}")
def actualizar_demo(
    id_demo: int,
    demo: DemoUpdate,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    if user and user.get("rol") == "INVITADO":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El perfil Invitado no puede editar demos.")
    demo_service.actualizar_demo(id_demo, demo)
    return {"mensaje": "Demo actualizada"}


@router.delete("/{id_demo}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_demo(
    id_demo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    if user and user.get("rol") == "INVITADO":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El perfil Invitado no puede eliminar demos.")
    demo_service.eliminar_demo(id_demo)
    return None


@router.post("/{id_demo}/movimientos", status_code=status.HTTP_201_CREATED)
def agregar_movimiento_demo(
    id_demo: int,
    mov: MovimientoDemoCreate,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    if mov.id_demo != id_demo:
        raise HTTPException(status_code=400, detail="El ID no coincide")
    if mov.duracion_ms < 100 or mov.duracion_ms > 10000:
        raise HTTPException(status_code=422, detail="La duración del paso debe estar entre 100 ms y 10,000 ms por seguridad física.")
    if mov.pausa_ms < 0 or mov.pausa_ms > 5000:
        raise HTTPException(status_code=422, detail="La pausa entre pasos debe estar entre 0 ms y 5,000 ms.")

    demo_service.agregar_movimiento(mov)
    return {"mensaje": "Movimiento agregado"}


@router.get("/{id_demo}/movimientos", response_model=List[MovimientoDemoResponse])
def obtener_movimientos_demo(id_demo: int):
    return demo_service.obtener_movimientos(id_demo)


@router.put("/movimientos/{id_demo_movimiento}")
def actualizar_movimiento_demo(
    id_demo_movimiento: int,
    mov: MovimientoDemoUpdate,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    if mov.duracion_ms < 100 or mov.duracion_ms > 10000:
        raise HTTPException(status_code=422, detail="La duración del paso debe estar entre 100 ms y 10,000 ms.")
    demo_service.actualizar_movimiento(id_demo_movimiento, mov)
    return {"mensaje": "Movimiento actualizado"}


@router.delete("/movimientos/{id_demo_movimiento}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_movimiento_demo(
    id_demo_movimiento: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    demo_service.eliminar_movimiento(id_demo_movimiento)
    return None


async def tarea_ejecutar_demo(id_demo: int, id_vehiculo: int):
    """Tarea asíncrona de fondo que ejecuta la secuencia de movimientos."""
    id_cmd_detener = _obtener_id_comando_detener(id_vehiculo)
    try:
        movimientos = demo_service.obtener_movimientos(id_demo)
        if not movimientos:
            return
        
        await ws_manager.broadcast_json({"tipo_evento": "inicio_demo", "vehiculo": id_vehiculo})
        
        for mov in movimientos:
            duracion_segundos = min(max(mov.get('duracion_ms', 1000), 100), 10000) / 1000.0
            pausa_segundos = min(max(mov.get('pausa_ms', 500), 0), 5000) / 1000.0
            id_cmd_actual = mov.get('id_comando')
            
            # Actualizamos el estado en la BD en cada paso (sin ensuciar historial individual)
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
            await asyncio.sleep(duracion_segundos)
            await asyncio.sleep(pausa_segundos)

        # Al terminar normalmente, enviamos comando Detener real del vehículo
        estado_final = EstadoVehiculoUpdate(id_vehiculo=id_vehiculo, id_comando=id_cmd_detener, conectado=True)
        telemetria_service.actualizar_estado(estado_final)
        await ws_manager.broadcast_json({"tipo_evento": "fin_demo", "vehiculo": id_vehiculo})

    except asyncio.CancelledError:
        pass

    finally:
        if id_vehiculo in active_demo_tasks:
            del active_demo_tasks[id_vehiculo]


@router.post("/{id_demo}/ejecutar")
async def iniciar_ejecucion_demo(
    id_demo: int,
    id_vehiculo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    """Inicia la demo validando autorización por recurso y bloquea ejecuciones simultáneas."""
    verificar_acceso_vehiculo(id_vehiculo, user, modo="control")

    if id_vehiculo in active_demo_tasks:
        raise HTTPException(
            status_code=400, 
            detail=f"El vehículo {id_vehiculo} ya está ejecutando una DEMO. Cancele la actual o espere."
        )

    tarea = asyncio.create_task(tarea_ejecutar_demo(id_demo, id_vehiculo))
    active_demo_tasks[id_vehiculo] = tarea

    return {"mensaje": "Secuencia DEMO iniciada", "vehiculo": id_vehiculo, "demo": id_demo}


@router.post("/vehiculo/{id_vehiculo}/cancelar")
async def cancelar_ejecucion_demo(
    id_vehiculo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    """Detiene de forma prioritaria la ejecución si hay una DEMO en curso."""
    verificar_acceso_vehiculo(id_vehiculo, user, modo="control")
    id_cmd_detener = _obtener_id_comando_detener(id_vehiculo)
    try:
        if id_vehiculo not in active_demo_tasks:
            return {"mensaje": "No hay ninguna DEMO en curso para este vehículo."}
        
        tarea_activa = active_demo_tasks.pop(id_vehiculo)
        tarea_activa.cancel()
        
        estado_cancelado = EstadoVehiculoUpdate(id_vehiculo=id_vehiculo, id_comando=id_cmd_detener, conectado=True)
        telemetria_service.actualizar_estado(estado_cancelado)
        
        await ws_manager.broadcast_json({"tipo_evento": "cancelacion_demo", "vehiculo": id_vehiculo})
        
        return {"mensaje": f"Se ha enviado la señal de detención al vehículo {id_vehiculo}."}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno al cancelar: {str(e)}")
