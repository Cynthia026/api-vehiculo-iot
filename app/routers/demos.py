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
    registrar_auditoria,
    get_current_user,
    verificar_lectura_demo,
    verificar_edicion_demo,
    obtener_demo,
    COMANDOS_INVITADO
)
from app.database import db_manager

router = APIRouter(prefix="/api/demos", tags=["Secuencias DEMO"])

# --- DICCIONARIO GLOBAL DE TAREAS EN CURSO ---
# Guarda las tareas activas para evitar simultaneidad y permitir cancelación
active_demo_tasks: Dict[int, asyncio.Task] = {}


_pk_movimientos: Optional[str] = None


def _columna_pk_movimientos() -> str:
    """Nombre real de la llave primaria de demo_movimientos (se consulta una vez en INFORMATION_SCHEMA)."""
    global _pk_movimientos
    if _pk_movimientos:
        return _pk_movimientos
    filas = db_manager.execute_query(
        """
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'demo_movimientos' AND CONSTRAINT_NAME = 'PRIMARY'
        LIMIT 1
        """
    )
    nombre = (filas[0].get("COLUMN_NAME") if filas else None) or "id_demo_movimiento"
    if not nombre.replace("_", "").isalnum():
        nombre = "id_demo_movimiento"
    _pk_movimientos = nombre
    return nombre


def _demo_de_movimiento(id_demo_movimiento: int) -> int:
    pk = _columna_pk_movimientos()
    filas = db_manager.execute_query(f"SELECT id_demo FROM demo_movimientos WHERE {pk} = %s LIMIT 1", (id_demo_movimiento,))
    if not filas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Paso {id_demo_movimiento} no encontrado")
    return int(filas[0]["id_demo"])


def _validar_comando_paso(id_comando: int, id_vehiculo: int) -> None:
    """El paso sólo puede usar un comando habilitado de la misma unidad (compatible con su hardware)."""
    filas = db_manager.execute_query(
        "SELECT activo FROM comandos WHERE id_comando = %s AND id_vehiculo = %s LIMIT 1",
        (id_comando, id_vehiculo)
    )
    if not filas:
        raise HTTPException(status_code=422, detail="El comando no pertenece a la unidad de esta demo.")
    if not filas[0].get("activo"):
        raise HTTPException(status_code=422, detail="El comando no está habilitado para esta unidad.")


def _validar_tiempos(duracion_ms: int, pausa_ms: int) -> None:
    if duracion_ms < 100 or duracion_ms > 10000:
        raise HTTPException(status_code=422, detail="La duración del paso debe estar entre 100 ms y 10,000 ms por seguridad física.")
    if pausa_ms < 0 or pausa_ms > 5000:
        raise HTTPException(status_code=422, detail="La pausa entre pasos debe estar entre 0 ms y 5,000 ms.")


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
    await ws_manager.connect(websocket, id_vehiculo)
    try:
        while True:
            raw_text = await websocket.receive_text()
            # Autenticación segura por mensaje JSON (sin exponer JWT en la URL ni en logs del servidor)
            try:
                import json
                msg = json.loads(raw_text)
                if isinstance(msg, dict) and msg.get("tipo_evento") == "auth_ws" and msg.get("token"):
                    user = decode_access_token(msg["token"])
                    verificar_acceso_vehiculo(id_vehiculo, user, modo="lectura")
            except HTTPException:
                ws_manager.disconnect(websocket, id_vehiculo)
                await websocket.close(code=4003)
                return
            except Exception:
                pass
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
    user: Dict[str, Any] = Depends(get_current_user)
):
    if user.get("rol") == "INVITADO":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El perfil Invitado no puede crear nuevas demos.")

    verificar_acceso_vehiculo(demo.id_vehiculo, user, modo="control" if user.get("rol") == "USUARIO" else "lectura")
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
    verificar_edicion_demo(id_demo, user)
    demo_service.actualizar_demo(id_demo, demo)
    registrar_auditoria(user.get("id_usuario"), user.get("rol"), "EDICION_DEMO", "demos", id_demo,
                        f"Demo #{id_demo} actualizada ('{demo.nombre}', activo={demo.activo})")
    return {"mensaje": "Demo actualizada"}


@router.delete("/{id_demo}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_demo(
    id_demo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    demo_info = verificar_edicion_demo(id_demo, user)
    demo_service.eliminar_demo(id_demo)
    registrar_auditoria(user.get("id_usuario"), user.get("rol"), "ELIMINACION_DEMO", "demos", id_demo,
                        f"Demo #{id_demo} '{demo_info.get('nombre')}' eliminada")
    return None


@router.post("/{id_demo}/movimientos", status_code=status.HTTP_201_CREATED)
def agregar_movimiento_demo(
    id_demo: int,
    mov: MovimientoDemoCreate,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    if mov.id_demo != id_demo:
        raise HTTPException(status_code=400, detail="El ID no coincide")
    _validar_tiempos(mov.duracion_ms, mov.pausa_ms)
    demo_info = verificar_edicion_demo(id_demo, user)
    _validar_comando_paso(mov.id_comando, demo_info["id_vehiculo"])

    demo_service.agregar_movimiento(mov)
    registrar_auditoria(user.get("id_usuario"), user.get("rol"), "PASO_DEMO_AGREGADO", "demo_movimientos", id_demo,
                        f"Paso #{mov.orden} (comando {mov.id_comando}, {mov.duracion_ms} ms) agregado a demo #{id_demo}")
    return {"mensaje": "Movimiento agregado"}


@router.get("/{id_demo}/movimientos", response_model=List[MovimientoDemoResponse])
def obtener_movimientos_demo(
    id_demo: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    verificar_lectura_demo(id_demo, user)
    return demo_service.obtener_movimientos(id_demo)


@router.put("/movimientos/{id_demo_movimiento}")
def actualizar_movimiento_demo(
    id_demo_movimiento: int,
    mov: MovimientoDemoUpdate,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    _validar_tiempos(mov.duracion_ms, mov.pausa_ms)
    id_demo = _demo_de_movimiento(id_demo_movimiento)
    demo_info = verificar_edicion_demo(id_demo, user)
    _validar_comando_paso(mov.id_comando, demo_info["id_vehiculo"])
    demo_service.actualizar_movimiento(id_demo_movimiento, mov)
    registrar_auditoria(user.get("id_usuario"), user.get("rol"), "PASO_DEMO_EDITADO", "demo_movimientos", id_demo,
                        f"Paso {id_demo_movimiento} de demo #{id_demo} actualizado")
    return {"mensaje": "Movimiento actualizado"}


@router.delete("/movimientos/{id_demo_movimiento}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_movimiento_demo(
    id_demo_movimiento: int,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    id_demo = _demo_de_movimiento(id_demo_movimiento)
    verificar_edicion_demo(id_demo, user)
    demo_service.eliminar_movimiento(id_demo_movimiento)
    registrar_auditoria(user.get("id_usuario"), user.get("rol"), "PASO_DEMO_ELIMINADO", "demo_movimientos", id_demo,
                        f"Paso {id_demo_movimiento} eliminado de demo #{id_demo}")
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
    demo_info = verificar_lectura_demo(id_demo, user)
    if int(demo_info["id_vehiculo"]) != int(id_vehiculo):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta demo pertenece a otra unidad.")
    if user.get("rol") == "INVITADO":
        # El Invitado sólo ejecuta demos cuyos pasos usen comandos permitidos para él
        pasos = demo_service.obtener_movimientos(id_demo)
        nombres = {int(c["id_comando"]): str(c["nombre"]).strip().upper() for c in db_manager.execute_query(
            "SELECT id_comando, nombre FROM comandos WHERE id_vehiculo = %s", (id_vehiculo,))}
        prohibidos = {nombres.get(int(p.get("id_comando") or 0), "DESCONOCIDO") for p in pasos} - COMANDOS_INVITADO
        if prohibidos:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Esta demo usa comandos no permitidos para Invitado: {', '.join(sorted(prohibidos))}.")

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
