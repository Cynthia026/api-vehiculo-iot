from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any, List, Optional
from app.database import db_manager
import secrets
from fastapi.encoders import jsonable_encoder
from app.security import (
    require_roles, hash_password, registrar_auditoria, limpiar_sesiones_expiradas,
    obtener_prestamo_activo, TIPO_PRESTAMO_FISICO, UNIDAD_FISICA_ID, GUEST_TTL_SECONDS,
    SOLICITUD_PENDIENTE_TTL_SECONDS
)
from app.schemas.administracion import (
    ModeloCatalogoCreate,
    UnidadAdminCreate,
    UnidadAdminUpdate,
    ClienteCreate,
    AsignacionCreate,
    ModeloCatalogoUpdate,
    ClienteUpdate,
    ESTADOS_COMERCIALES
)

router = APIRouter(prefix="/api/admin", tags=["Administración Comercial (4.3)"])


@router.get("/dashboard")
def obtener_dashboard_admin(user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    """
    Devuelve métricas reales de RDS, inventario de unidades con propietario,
    modelos comerciales, clientes compradores y bitácora reciente.
    """
    limpiar_sesiones_expiradas()

    unidades = db_manager.execute_query(
        """
        SELECT v.id_vehiculo, v.nombre, v.modelo, v.descripcion, v.microcontrolador,
               v.fecha_registro, v.activo, v.id_modelo,
               COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
               COALESCE(v.estado_comercial, 'DISPONIBLE') AS estado_comercial,
               COALESCE(v.soporte_autorizado, 0) AS soporte_autorizado,
               v.soporte_expira_en,
               a.id_asignacion,
               a.id_usuario AS id_propietario,
               u.nombre AS nombre_propietario,
               u.email AS email_propietario,
               ev.conectado,
               c.nombre AS ultimo_comando,
               ev.fecha_actualizacion
        FROM vehiculos v
        LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
        LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
        LEFT JOIN estado_vehiculo ev ON ev.id_vehiculo = v.id_vehiculo
        LEFT JOIN comandos c ON c.id_comando = ev.id_comando
        ORDER BY v.id_vehiculo
        """
    )

    modelos = db_manager.execute_query(
        "SELECT * FROM modelos_catalogo ORDER BY id_modelo"
    )

    clientes = db_manager.execute_query(
        """
        SELECT u.id_usuario, u.nombre, u.email, u.activo, u.fecha_registro,
               r.codigo AS rol,
               COUNT(a.id_asignacion) AS total_unidades
        FROM usuarios u
        INNER JOIN roles r ON r.id_rol = u.id_rol
        LEFT JOIN asignaciones_vehiculo a ON a.id_usuario = u.id_usuario AND a.activo = 1
        WHERE r.codigo = 'USUARIO'
        GROUP BY u.id_usuario, u.nombre, u.email, u.activo, u.fecha_registro, r.codigo
        ORDER BY u.id_usuario
        """
    )

    sesiones_activas = db_manager.execute_query(
        """
        SELECT s.id_sesion, s.id_vehiculo, v.nombre AS nombre_vehiculo,
               s.nombre_operador, s.tipo_sesion, s.inicio_en, s.expira_en,
               TIMESTAMPDIFF(SECOND, NOW(), s.expira_en) AS segundos_restantes
        FROM sesiones_control s
        INNER JOIN vehiculos v ON v.id_vehiculo = s.id_vehiculo
        WHERE s.activa = 1 AND s.expira_en > NOW()
        ORDER BY s.inicio_en DESC
        """
    )

    auditoria = db_manager.execute_query(
        """
        SELECT b.id_auditoria, b.id_usuario, COALESCE(u.nombre, 'Visitante / Sistema') AS actor,
               b.rol, b.accion, b.entidad, b.id_recurso, b.detalle, b.fecha_hora
        FROM bitacora_auditoria b
        LEFT JOIN usuarios u ON u.id_usuario = b.id_usuario
        ORDER BY b.id_auditoria DESC
        LIMIT 25
        """
    )

    total_unidades = len(unidades)
    vendidas = sum(1 for u in unidades if u.get("estado_comercial") == "VENDIDO")
    exhibicion = sum(1 for u in unidades if u.get("estado_comercial") == "EXHIBICION")
    disponibles = sum(1 for u in unidades if u.get("estado_comercial") == "DISPONIBLE")

    return {
        "metricas": {
            "total_unidades": total_unidades,
            "unidades_vendidas": vendidas,
            "unidades_exhibicion": exhibicion,
            "unidades_disponibles": disponibles,
            "total_modelos": len(modelos),
            "total_clientes": len(clientes),
            "sesiones_invitado_activas": len(sesiones_activas)
        },
        "unidades": unidades,
        "modelos": modelos,
        "clientes": clientes,
        "sesiones_activas": sesiones_activas,
        "auditoria": auditoria
    }


@router.get("/modelos")
def listar_modelos(user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    return db_manager.execute_query("SELECT * FROM modelos_catalogo ORDER BY id_modelo")


@router.post("/modelos", status_code=status.HTTP_201_CREATED)
def crear_modelo(modelo: ModeloCatalogoCreate, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    existe = db_manager.execute_query(
        "SELECT id_modelo FROM modelos_catalogo WHERE UPPER(codigo_modelo) = UPPER(%s)",
        (modelo.codigo_modelo.strip(),)
    )
    if existe:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El código de modelo comercial ya existe.")

    res = db_manager.execute_write(
        """
        INSERT INTO modelos_catalogo (codigo_modelo, nombre, descripcion, microcontrolador_default, tiene_brazo, tiene_motores_giro, activo)
        VALUES (%s, %s, %s, %s, %s, %s, 1)
        """,
        (
            modelo.codigo_modelo.strip().upper(),
            modelo.nombre.strip(),
            modelo.descripcion,
            modelo.microcontrolador_default.strip(),
            1 if modelo.tiene_brazo else 0,
            1 if modelo.tiene_motores_giro else 0
        )
    )
    id_nuevo = res["lastrowid"]
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "ALTA_MODELO", "modelos_catalogo", id_nuevo,
        f"Modelo comercial '{modelo.nombre}' ({modelo.codigo_modelo}) registrado"
    )
    creado = db_manager.execute_query("SELECT * FROM modelos_catalogo WHERE id_modelo = %s", (id_nuevo,))
    return creado[0] if creado else {"id_modelo": id_nuevo}


@router.put("/modelos/{id_modelo}")
def actualizar_modelo(id_modelo: int, datos: ModeloCatalogoUpdate, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    """Edita o desactiva (activo = false) un modelo comercial. No se borra para conservar las unidades asociadas."""
    existe = db_manager.execute_query("SELECT id_modelo FROM modelos_catalogo WHERE id_modelo = %s", (id_modelo,))
    if not existe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modelo no encontrado")
    db_manager.execute_write(
        """
        UPDATE modelos_catalogo
        SET nombre = %s, descripcion = %s, microcontrolador_default = %s,
            tiene_brazo = %s, tiene_motores_giro = %s, activo = %s
        WHERE id_modelo = %s
        """,
        (datos.nombre.strip(), datos.descripcion, datos.microcontrolador_default.strip(),
         1 if datos.tiene_brazo else 0, 1 if datos.tiene_motores_giro else 0, 1 if datos.activo else 0, id_modelo)
    )
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "EDICION_MODELO" if datos.activo else "DESACTIVACION_MODELO", "modelos_catalogo", id_modelo,
        f"Modelo #{id_modelo} '{datos.nombre}' actualizado (activo={datos.activo})"
    )
    return db_manager.execute_query("SELECT * FROM modelos_catalogo WHERE id_modelo = %s", (id_modelo,))[0]


@router.post("/unidades", status_code=status.HTTP_201_CREATED)
def registrar_unidad_fisica(unidad: UnidadAdminCreate, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    """
    Registra una nueva unidad física en `vehiculos`, clona la plantilla de comandos
    del modelo comercial e inicializa su registro en `estado_vehiculo`.
    """
    if unidad.estado_comercial not in ("DISPONIBLE", "EXHIBICION", "MANTENIMIENTO"):
        raise HTTPException(status_code=422, detail="Una unidad nueva sólo puede ser DISPONIBLE, EXHIBICION o MANTENIMIENTO (VENDIDO se asigna desde Asignaciones).")
    serie = unidad.numero_serie.strip().upper()
    if len(serie) < 3:
        raise HTTPException(status_code=422, detail="El número de serie debe tener al menos 3 caracteres.")
    dup = db_manager.execute_query("SELECT id_vehiculo FROM vehiculos WHERE UPPER(numero_serie) = %s", (serie,))
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El número de serie '{serie}' ya está registrado.")

    nombre_modelo = unidad.modelo or "Excavadora IoT"
    tiene_brazo = True
    if unidad.id_modelo:
        mod = db_manager.execute_query("SELECT * FROM modelos_catalogo WHERE id_modelo = %s", (unidad.id_modelo,))
        if not mod:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El modelo comercial no existe.")
        if not mod[0].get("activo", 1):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El modelo comercial está desactivado.")
        if mod:
            nombre_modelo = mod[0]["nombre"]
            tiene_brazo = bool(mod[0].get("tiene_brazo", 1))

    res = db_manager.execute_write(
        """
        INSERT INTO vehiculos (nombre, modelo, descripcion, microcontrolador, activo, id_modelo, numero_serie, estado_comercial, soporte_autorizado)
        VALUES (%s, %s, %s, %s, 1, %s, %s, %s, 0)
        """,
        (
            unidad.nombre.strip(),
            nombre_modelo,
            unidad.descripcion,
            unidad.microcontrolador.strip(),
            unidad.id_modelo,
            serie,
            unidad.estado_comercial
        )
    )
    id_nuevo = res["lastrowid"]

    # Clonar comandos base desde la Unidad 1 respetando si el modelo tiene brazo hidráulico
    db_manager.execute_write(
        """
        INSERT INTO comandos (id_vehiculo, nombre, codigo, descripcion, activo)
        SELECT %s, c.nombre, c.codigo, c.descripcion,
               CASE WHEN %s = 0 AND c.nombre IN ('SUBIR_BRAZO', 'BAJAR_BRAZO') THEN 0 ELSE c.activo END
        FROM comandos c
        WHERE c.id_vehiculo = 1
        """,
        (id_nuevo, 1 if tiene_brazo else 0)
    )

    # Inicializar fila en estado_vehiculo con el comando Detener de la nueva unidad
    cmd_stop = db_manager.execute_query(
        "SELECT id_comando FROM comandos WHERE id_vehiculo = %s AND LOWER(nombre) = 'detener' LIMIT 1",
        (id_nuevo,)
    )
    if cmd_stop:
        db_manager.execute_write(
            "INSERT INTO estado_vehiculo (id_vehiculo, id_comando, conectado) VALUES (%s, %s, 1)",
            (id_nuevo, cmd_stop[0]["id_comando"])
        )

    registrar_auditoria(
        user["id_usuario"], "ADMIN", "ALTA_UNIDAD", "vehiculos", id_nuevo,
        f"Unidad física '{unidad.nombre}' (Serie: {serie}, Estado: {unidad.estado_comercial}) creada"
    )
    nueva = db_manager.execute_query("SELECT * FROM vehiculos WHERE id_vehiculo = %s", (id_nuevo,))
    return nueva[0] if nueva else {"id_vehiculo": id_nuevo}


@router.put("/unidades/{id_vehiculo}")
def actualizar_unidad_fisica(
    id_vehiculo: int,
    datos: UnidadAdminUpdate,
    user: Dict[str, Any] = Depends(require_roles("ADMIN"))
):
    if datos.estado_comercial not in ESTADOS_COMERCIALES:
        raise HTTPException(status_code=422, detail=f"Estado no válido. Usa: {', '.join(ESTADOS_COMERCIALES)}")
    actual = db_manager.execute_query(
        """
        SELECT v.id_vehiculo, a.id_usuario AS id_propietario FROM vehiculos v
        LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
        WHERE v.id_vehiculo = %s LIMIT 1
        """,
        (id_vehiculo,)
    )
    if not actual:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad no encontrada")
    tiene_dueno = bool(actual[0].get("id_propietario"))
    if tiene_dueno and (datos.estado_comercial != "VENDIDO" or not datos.activo):
        raise HTTPException(status_code=409, detail="La unidad tiene comprador: revoca la asignación antes de cambiar su estado o darla de baja.")
    if not tiene_dueno and datos.estado_comercial == "VENDIDO":
        raise HTTPException(status_code=409, detail="Para marcarla como VENDIDO asígnala a un comprador.")
    if datos.numero_serie:
        dup = db_manager.execute_query(
            "SELECT id_vehiculo FROM vehiculos WHERE UPPER(numero_serie) = %s AND id_vehiculo <> %s",
            (datos.numero_serie.strip().upper(), id_vehiculo)
        )
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese número de serie ya pertenece a otra unidad.")
    db_manager.execute_write(
        """
        UPDATE vehiculos
        SET nombre = %s, modelo = %s, numero_serie = COALESCE(%s, numero_serie),
            descripcion = %s, microcontrolador = %s, estado_comercial = %s, activo = %s
        WHERE id_vehiculo = %s
        """,
        (
            datos.nombre.strip(),
            datos.modelo.strip(),
            datos.numero_serie.strip().upper() if datos.numero_serie else None,
            datos.descripcion,
            datos.microcontrolador.strip(),
            datos.estado_comercial,
            1 if datos.activo else 0,
            id_vehiculo
        )
    )
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "EDICION_UNIDAD", "vehiculos", id_vehiculo,
        f"Unidad #{id_vehiculo} actualizada ({datos.nombre}, Estado: {datos.estado_comercial})"
    )
    actualizado = db_manager.execute_query("SELECT * FROM vehiculos WHERE id_vehiculo = %s", (id_vehiculo,))
    return actualizado[0] if actualizado else {"id_vehiculo": id_vehiculo}


@router.get("/clientes")
def listar_clientes(user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    return db_manager.execute_query(
        """
        SELECT u.id_usuario, u.nombre, u.email, u.activo, u.fecha_registro,
               COUNT(a.id_asignacion) AS total_unidades
        FROM usuarios u
        INNER JOIN roles r ON r.id_rol = u.id_rol
        LEFT JOIN asignaciones_vehiculo a ON a.id_usuario = u.id_usuario AND a.activo = 1
        WHERE r.codigo = 'USUARIO'
        GROUP BY u.id_usuario, u.nombre, u.email, u.activo, u.fecha_registro
        ORDER BY u.id_usuario
        """
    )


@router.post("/clientes", status_code=status.HTTP_201_CREATED)
def registrar_cliente(cliente: ClienteCreate, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    email = cliente.email.strip().lower()
    dup = db_manager.execute_query("SELECT id_usuario FROM usuarios WHERE LOWER(email) = %s", (email,))
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo electrónico ya está registrado.")

    rol_user = db_manager.execute_query("SELECT id_rol FROM roles WHERE codigo = 'USUARIO' LIMIT 1")
    id_rol = rol_user[0]["id_rol"] if rol_user else 2

    pwd_hash = hash_password(cliente.password)
    res = db_manager.execute_write(
        """
        INSERT INTO usuarios (id_rol, nombre, email, password_hash, activo)
        VALUES (%s, %s, %s, %s, 1)
        """,
        (id_rol, cliente.nombre.strip(), email, pwd_hash)
    )
    id_nuevo = res["lastrowid"]
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "ALTA_CLIENTE", "usuarios", id_nuevo,
        f"Cliente comprador '{cliente.nombre}' ({email}) registrado"
    )
    return {
        "id_usuario": id_nuevo,
        "nombre": cliente.nombre.strip(),
        "email": email,
        "activo": 1
    }


@router.put("/clientes/{id_usuario}")
def actualizar_cliente(id_usuario: int, datos: ClienteUpdate, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    """Edita, desactiva (activo = false) o restablece la contraseña de un comprador. Nunca se borra."""
    cliente = db_manager.execute_query(
        """
        SELECT u.id_usuario FROM usuarios u INNER JOIN roles r ON r.id_rol = u.id_rol
        WHERE u.id_usuario = %s AND r.codigo = 'USUARIO' LIMIT 1
        """,
        (id_usuario,)
    )
    if not cliente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente comprador no encontrado")
    email = datos.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="Correo electrónico no válido.")
    dup = db_manager.execute_query(
        "SELECT id_usuario FROM usuarios WHERE LOWER(email) = %s AND id_usuario <> %s", (email, id_usuario)
    )
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya pertenece a otra cuenta.")
    db_manager.execute_write(
        "UPDATE usuarios SET nombre = %s, email = %s, activo = %s WHERE id_usuario = %s",
        (datos.nombre.strip(), email, 1 if datos.activo else 0, id_usuario)
    )
    if datos.password:
        db_manager.execute_write("UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s",
                                 (hash_password(datos.password), id_usuario))
    if not datos.activo:
        # Un comprador desactivado ya no puede autorizar soporte sobre sus unidades
        db_manager.execute_write(
            """
            UPDATE vehiculos v INNER JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
            SET v.soporte_autorizado = 0, v.soporte_expira_en = NULL
            WHERE a.id_usuario = %s
            """,
            (id_usuario,)
        )
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "EDICION_CLIENTE" if datos.activo else "DESACTIVACION_CLIENTE", "usuarios", id_usuario,
        f"Cliente #{id_usuario} actualizado (activo={datos.activo}{', contraseña restablecida' if datos.password else ''})"
    )
    return {"id_usuario": id_usuario, "nombre": datos.nombre.strip(), "email": email, "activo": 1 if datos.activo else 0}


@router.post("/asignaciones", status_code=status.HTTP_201_CREATED)
def asignar_unidad_a_cliente(datos: AsignacionCreate, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    """Asigna una unidad física a un cliente comprador y marca la unidad como VENDIDO."""
    cliente = db_manager.execute_query(
        """
        SELECT u.id_usuario, u.activo FROM usuarios u INNER JOIN roles r ON r.id_rol = u.id_rol
        WHERE u.id_usuario = %s AND r.codigo = 'USUARIO' LIMIT 1
        """,
        (datos.id_usuario,)
    )
    if not cliente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El cliente comprador no existe.")
    if not cliente[0].get("activo"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El cliente está desactivado.")
    unidad = db_manager.execute_query(
        """
        SELECT v.id_vehiculo, v.activo, a.id_usuario AS id_anterior FROM vehiculos v
        LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
        WHERE v.id_vehiculo = %s LIMIT 1
        """,
        (datos.id_vehiculo,)
    )
    if not unidad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La unidad no existe.")
    if not unidad[0].get("activo"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La unidad está dada de baja.")
    sesion = db_manager.execute_query(
        "SELECT 1 FROM sesiones_control WHERE id_vehiculo = %s AND activa = 1 AND expira_en > NOW() LIMIT 1",
        (datos.id_vehiculo,)
    )
    if sesion:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un Invitado está usando la unidad en este momento; espera a que termine su prueba.")
    id_anterior = unidad[0].get("id_anterior")

    # Desactivar asignaciones previas de esa unidad (se conservan como historial: activo = 0)
    db_manager.execute_write(
        "UPDATE asignaciones_vehiculo SET activo = 0 WHERE id_vehiculo = %s AND activo = 1",
        (datos.id_vehiculo,)
    )

    res = db_manager.execute_write(
        """
        INSERT INTO asignaciones_vehiculo (id_vehiculo, id_usuario, notas, activo)
        VALUES (%s, %s, %s, 1)
        """,
        (datos.id_vehiculo, datos.id_usuario, datos.notas or "Asignación comercial desde panel Admin")
    )

    db_manager.execute_write(
        "UPDATE vehiculos SET estado_comercial = 'VENDIDO', soporte_autorizado = 0 WHERE id_vehiculo = %s",
        (datos.id_vehiculo,)
    )

    registrar_auditoria(
        user["id_usuario"], "ADMIN", "ASIGNACION_UNIDAD", "asignaciones_vehiculo", datos.id_vehiculo,
        f"Unidad #{datos.id_vehiculo} asignada al cliente #{datos.id_usuario}"
        + (f" (permisos del titular anterior #{id_anterior} revocados)" if id_anterior and id_anterior != datos.id_usuario else "")
    )
    return {
        "id_asignacion": res["lastrowid"],
        "id_vehiculo": datos.id_vehiculo,
        "id_usuario": datos.id_usuario,
        "mensaje": "Unidad asignada exitosamente al comprador."
    }


@router.delete("/asignaciones/{id_vehiculo}")
def revocar_asignacion_unidad(
    id_vehiculo: int,
    nuevo_estado: str = "DISPONIBLE",
    user: Dict[str, Any] = Depends(require_roles("ADMIN"))
):
    """Desvincula la unidad del comprador actual y actualiza su estado comercial (DISPONIBLE o EXHIBICION)."""
    db_manager.execute_write(
        "UPDATE asignaciones_vehiculo SET activo = 0 WHERE id_vehiculo = %s AND activo = 1",
        (id_vehiculo,)
    )
    estado_valido = nuevo_estado if nuevo_estado in ("DISPONIBLE", "EXHIBICION", "MANTENIMIENTO") else "DISPONIBLE"
    db_manager.execute_write(
        "UPDATE vehiculos SET estado_comercial = %s, soporte_autorizado = 0, soporte_expira_en = NULL WHERE id_vehiculo = %s",
        (estado_valido, id_vehiculo)
    )
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "REVOCACION_UNIDAD", "asignaciones_vehiculo", id_vehiculo,
        f"Asignación de unidad #{id_vehiculo} revocada -> nuevo estado: {estado_valido}"
    )
    return {"mensaje": f"Asignación revocada. La unidad #{id_vehiculo} ahora está en estado {estado_valido}."}


@router.get("/auditoria")
def consultar_bitacora(limit: int = 40, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    return db_manager.execute_query(
        """
        SELECT b.id_auditoria, b.id_usuario, COALESCE(u.nombre, 'Visitante / Sistema') AS actor,
               b.rol, b.accion, b.entidad, b.id_recurso, b.detalle, b.fecha_hora
        FROM bitacora_auditoria b
        LEFT JOIN usuarios u ON u.id_usuario = b.id_usuario
        ORDER BY b.id_auditoria DESC
        LIMIT %s
        """,
        (min(limit, 100),)
    )



# ---------------------------------------------------------------------------------------------
# SOLICITUDES DE INVITADO PARA MANEJAR EL VEHÍCULO FÍSICO
# ---------------------------------------------------------------------------------------------

def _expirar_solicitudes_pendientes() -> None:
    db_manager.execute_write(
        """
        UPDATE solicitudes_invitado SET estado = 'EXPIRADA', resuelta_en = NOW()
        WHERE estado = 'PENDIENTE' AND creada_en <= NOW() - INTERVAL %s SECOND
        """,
        (SOLICITUD_PENDIENTE_TTL_SECONDS,)
    )


async def _detener_unidad(id_vehiculo: int) -> None:
    """Cancela la demo en curso y manda DETENER (al cambiar de operador el vehículo debe quedar quieto)."""
    from app.routers.demos import active_demo_tasks, _obtener_id_comando_detener
    from app.services.telemetria_service import telemetria_service
    from app.schemas.estado import EstadoVehiculoUpdate
    from app.websocket.manager import ws_manager
    tarea = active_demo_tasks.pop(int(id_vehiculo), None)
    if tarea:
        tarea.cancel()
    try:
        id_stop = _obtener_id_comando_detener(id_vehiculo)
        estado = telemetria_service.actualizar_estado(EstadoVehiculoUpdate(id_vehiculo=id_vehiculo, id_comando=id_stop, conectado=True))
        await ws_manager.broadcast_json({
            "tipo_evento": "movimiento_individual", "vehiculo": id_vehiculo,
            "datos": jsonable_encoder(estado or {"id_vehiculo": id_vehiculo, "id_comando": id_stop, "comando": "DETENER"})
        })
    except Exception as e:
        print(f"[PRESTAMO STOP WARN] {e}")


@router.get("/solicitudes-invitado")
def listar_solicitudes_invitado(user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    """Solicitudes en espera y préstamo físico en curso (el panel del Admin las consulta cada pocos segundos)."""
    _expirar_solicitudes_pendientes()
    pendientes = db_manager.execute_query(
        """
        SELECT s.id_solicitud, s.id_vehiculo, s.nombre_visitante, s.creada_en,
               TIMESTAMPDIFF(SECOND, s.creada_en, NOW()) AS segundos_esperando
        FROM solicitudes_invitado s
        WHERE s.estado = 'PENDIENTE'
        ORDER BY s.creada_en
        """
    )
    unidad = db_manager.execute_query(
        """
        SELECT v.id_vehiculo, v.nombre, COALESCE(v.estado_comercial, 'DISPONIBLE') AS estado_comercial,
               u.nombre AS nombre_propietario
        FROM vehiculos v
        LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
        LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
        WHERE v.id_vehiculo = %s LIMIT 1
        """,
        (UNIDAD_FISICA_ID,)
    )
    return {
        "unidad_fisica": unidad[0] if unidad else {"id_vehiculo": UNIDAD_FISICA_ID, "nombre": f"Unidad #{UNIDAD_FISICA_ID}"},
        "prestamo_activo": obtener_prestamo_activo(UNIDAD_FISICA_ID),
        "pendientes": pendientes,
        "duracion_prestamo_seg": GUEST_TTL_SECONDS
    }


def _solicitud_pendiente(id_solicitud: int) -> Dict[str, Any]:
    _expirar_solicitudes_pendientes()
    filas = db_manager.execute_query(
        "SELECT id_solicitud, id_vehiculo, nombre_visitante, estado FROM solicitudes_invitado WHERE id_solicitud = %s LIMIT 1",
        (id_solicitud,)
    )
    if not filas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada.")
    if filas[0]["estado"] != "PENDIENTE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"La solicitud ya está {filas[0]['estado']}.")
    return filas[0]


@router.post("/solicitudes-invitado/{id_solicitud}/aprobar")
async def aprobar_solicitud_invitado(id_solicitud: int, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    """
    Presta el vehículo físico al visitante por 3 minutos con TODOS los comandos y demos de la empresa.
    Sólo un préstamo a la vez; el propietario queda bloqueado (409) mientras dure.
    """
    sol = _solicitud_pendiente(id_solicitud)
    id_v = int(sol["id_vehiculo"])
    unidad = db_manager.execute_query("SELECT activo FROM vehiculos WHERE id_vehiculo = %s LIMIT 1", (id_v,))
    if not unidad or not unidad[0].get("activo"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El vehículo físico está dado de baja.")
    ocupada = db_manager.execute_query(
        """
        SELECT nombre_operador, TIMESTAMPDIFF(SECOND, NOW(), expira_en) AS seg
        FROM sesiones_control WHERE id_vehiculo = %s AND activa = 1 AND expira_en > NOW() LIMIT 1
        """,
        (id_v,)
    )
    if ocupada:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya hay un Invitado manejando el vehículo ({ocupada[0]['nombre_operador']}, {max(1, int(ocupada[0]['seg'] or 1))} s restantes). Sólo uno a la vez."
        )

    # Marcar primero la solicitud (evita aprobar dos veces la misma si dos admins hacen clic)
    jti = secrets.token_hex(12)
    marcado = db_manager.execute_write(
        """
        UPDATE solicitudes_invitado SET estado = 'APROBADA', resuelta_en = NOW(), id_admin = %s, token_jti = %s
        WHERE id_solicitud = %s AND estado = 'PENDIENTE'
        """,
        (user["id_usuario"], jti, id_solicitud)
    )
    if not marcado.get("rowcount"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La solicitud ya fue atendida.")

    # El vehículo cambia de operador: se detiene lo que estuviera haciendo el dueño
    await _detener_unidad(id_v)

    sesion = db_manager.execute_write(
        """
        INSERT INTO sesiones_control (id_vehiculo, id_usuario, token_jti, nombre_operador, tipo_sesion, inicio_en, expira_en, activa)
        VALUES (%s, NULL, %s, %s, %s, NOW(), DATE_ADD(NOW(), INTERVAL %s SECOND), 1)
        """,
        (id_v, jti, sol["nombre_visitante"], TIPO_PRESTAMO_FISICO, GUEST_TTL_SECONDS)
    )
    db_manager.execute_write(
        "UPDATE solicitudes_invitado SET id_sesion = %s WHERE id_solicitud = %s",
        (sesion.get("lastrowid"), id_solicitud)
    )
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "APROBACION_PRESTAMO", "solicitudes_invitado", id_solicitud,
        f"Vehículo físico #{id_v} prestado a '{sol['nombre_visitante']}' por {GUEST_TTL_SECONDS} s"
    )
    return {"mensaje": f"Préstamo aprobado: '{sol['nombre_visitante']}' puede manejar la unidad #{id_v} por {GUEST_TTL_SECONDS // 60} minutos."}


@router.post("/solicitudes-invitado/{id_solicitud}/rechazar")
def rechazar_solicitud_invitado(id_solicitud: int, user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    sol = _solicitud_pendiente(id_solicitud)
    db_manager.execute_write(
        """
        UPDATE solicitudes_invitado SET estado = 'RECHAZADA', resuelta_en = NOW(), id_admin = %s
        WHERE id_solicitud = %s AND estado = 'PENDIENTE'
        """,
        (user["id_usuario"], id_solicitud)
    )
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "RECHAZO_PRESTAMO", "solicitudes_invitado", id_solicitud,
        f"Solicitud de '{sol['nombre_visitante']}' rechazada"
    )
    return {"mensaje": f"Solicitud de '{sol['nombre_visitante']}' rechazada."}


@router.post("/prestamo-fisico/terminar")
async def terminar_prestamo_fisico(user: Dict[str, Any] = Depends(require_roles("ADMIN"))):
    """El Admin corta el préstamo en curso: el vehículo se detiene y el token del Invitado deja de servir."""
    prestamo = obtener_prestamo_activo(UNIDAD_FISICA_ID)
    if not prestamo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay ningún préstamo en curso.")
    db_manager.execute_write("UPDATE sesiones_control SET activa = 0 WHERE id_sesion = %s", (prestamo["id_sesion"],))
    db_manager.execute_write(
        "UPDATE solicitudes_invitado SET estado = 'FINALIZADA' WHERE id_sesion = %s AND estado = 'APROBADA'",
        (prestamo["id_sesion"],)
    )
    await _detener_unidad(int(prestamo["id_vehiculo"]))
    from app.websocket.manager import ws_manager
    await ws_manager.broadcast_json({"tipo_evento": "sesion_invitado_expirada", "vehiculo": int(prestamo["id_vehiculo"])})
    registrar_auditoria(
        user["id_usuario"], "ADMIN", "FIN_PRESTAMO_ADMIN", "sesiones_control", prestamo["id_vehiculo"],
        f"Préstamo de '{prestamo['nombre_operador']}' terminado por el Administrador: unidad detenida"
    )
    return {"mensaje": "Préstamo terminado y vehículo detenido."}
