import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.encoders import jsonable_encoder
from typing import Dict, Any, Optional
from app.database import db_manager
from app.schemas.administracion import LoginRequest, GuestSessionRequest, SolicitudPrestamoRequest
from app.security import (
    verify_password,
    create_access_token,
    get_current_user,
    limpiar_sesiones_expiradas,
    registrar_auditoria,
    verificar_bloqueo_login,
    registrar_fallo_login,
    limpiar_fallos_login,
    revocar_token,
    TOKEN_TTL_SECONDS,
    GUEST_TTL_SECONDS,
    TIPO_PRESTAMO_FISICO,
    UNIDAD_FISICA_ID,
    SOLICITUD_PENDIENTE_TTL_SECONDS,
    MAX_SOLICITUDES_PENDIENTES,
    obtener_prestamo_activo
)
import hashlib
from app.services.telemetria_service import telemetria_service
from app.schemas.estado import EstadoVehiculoUpdate
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/api/auth", tags=["Autenticación y Sesiones (4.3)"])


def _obtener_unidades_permitidas(id_usuario: int, rol: str, id_reservado: Optional[int] = None):
    """Obtiene la lista de unidades físicas visibles según el rol y propietario."""
    if rol == "ADMIN":
        return db_manager.execute_query(
            """
            SELECT v.id_vehiculo, v.nombre, v.modelo, v.microcontrolador, v.activo,
                   COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
                   COALESCE(v.estado_comercial, 'DISPONIBLE') AS estado_comercial,
                   COALESCE(v.soporte_autorizado, 0) AS soporte_autorizado,
                   v.soporte_expira_en,
                   a.id_usuario AS id_propietario,
                   u.nombre AS nombre_propietario
            FROM vehiculos v
            LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
            LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
            WHERE v.activo = 1
            ORDER BY v.id_vehiculo
            """
        )
    if rol == "USUARIO":
        return db_manager.execute_query(
            """
            SELECT v.id_vehiculo, v.nombre, v.modelo, v.microcontrolador, v.activo,
                   COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
                   COALESCE(v.estado_comercial, 'VENDIDO') AS estado_comercial,
                   COALESCE(v.soporte_autorizado, 0) AS soporte_autorizado,
                   v.soporte_expira_en
            FROM vehiculos v
            INNER JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
            WHERE a.id_usuario = %s AND v.activo = 1
            ORDER BY v.id_vehiculo
            """,
            (id_usuario,)
        )
    # INVITADO con sesión: sólo la unidad que tiene reservada (exhibición o préstamo físico)
    if id_reservado:
        return db_manager.execute_query(
            """
            SELECT v.id_vehiculo, v.nombre, v.modelo, v.microcontrolador, v.activo,
                   COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
                   COALESCE(v.estado_comercial, 'EXHIBICION') AS estado_comercial
            FROM vehiculos v
            WHERE v.activo = 1 AND v.id_vehiculo = %s
            """,
            (id_reservado,)
        )
    # INVITADO: sólo unidades en estado EXHIBICION
    return db_manager.execute_query(
        """
        SELECT v.id_vehiculo, v.nombre, v.modelo, v.microcontrolador, v.activo,
               COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
               COALESCE(v.estado_comercial, 'EXHIBICION') AS estado_comercial
        FROM vehiculos v
        WHERE v.activo = 1 AND v.estado_comercial = 'EXHIBICION'
        ORDER BY v.id_vehiculo
        """
    )


@router.post("/login")
def iniciar_sesion(credenciales: LoginRequest, request: Request):
    """Inicia sesión para Administrador o Usuario Comprador verificando credenciales en RDS."""
    limpiar_sesiones_expiradas()
    email = credenciales.email.strip().lower()
    ip_cliente = request.client.host if request.client else "API"
    clave_intentos = f"{email}|{ip_cliente}"
    verificar_bloqueo_login(clave_intentos)   # 429 si superó el límite de intentos

    usuarios = db_manager.execute_query(
        """
        SELECT u.id_usuario, u.nombre, u.email, u.password_hash, u.activo,
               r.codigo AS rol, r.nombre AS nombre_rol
        FROM usuarios u
        INNER JOIN roles r ON r.id_rol = u.id_rol
        WHERE LOWER(u.email) = %s
        LIMIT 1
        """,
        (email,)
    )

    if not usuarios or not verify_password(credenciales.password, usuarios[0]["password_hash"]):
        registrar_fallo_login(clave_intentos)
        registrar_auditoria(
            usuarios[0]["id_usuario"] if usuarios else None, usuarios[0]["rol"] if usuarios else "DESCONOCIDO",
            "LOGIN_FALLIDO", "usuarios", usuarios[0]["id_usuario"] if usuarios else None,
            "Intento de inicio de sesión con credenciales incorrectas", ip_cliente
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo electrónico o contraseña incorrectos."
        )

    user = usuarios[0]
    if not user.get("activo"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta se encuentra desactivada. Contacta al Administrador."
        )

    limpiar_fallos_login(clave_intentos)
    jti = secrets.token_hex(12)
    token = create_access_token(
        {
            "id_usuario": user["id_usuario"],
            "nombre": user["nombre"],
            "email": user["email"],
            "rol": user["rol"],
            "jti": jti
        },
        expires_sec=TOKEN_TTL_SECONDS
    )

    unidades = _obtener_unidades_permitidas(user["id_usuario"], user["rol"])
    registrar_auditoria(
        user["id_usuario"], user["rol"], "LOGIN", "usuarios", user["id_usuario"],
        f"Inicio de sesión exitoso ({user['email']})", ip_cliente
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "usuario": {
            "id_usuario": user["id_usuario"],
            "nombre": user["nombre"],
            "email": user["email"],
            "rol": user["rol"],
            "nombre_rol": user["nombre_rol"]
        },
        "unidades": unidades
    }


@router.post("/invitado", status_code=status.HTTP_201_CREATED)
def iniciar_sesion_invitado(datos: GuestSessionRequest, request: Request):
    """
    Inicia una sesión temporal limitada (3 minutos) para un Invitado (cliente potencial)
    y le asigna en reserva exclusiva una unidad de EXHIBICIÓN disponible.
    """
    limpiar_sesiones_expiradas()

    # Buscar unidades de exhibición activas
    unidades_exhibicion = db_manager.execute_query(
        """
        SELECT id_vehiculo, nombre, modelo, numero_serie
        FROM vehiculos
        WHERE activo = 1 AND estado_comercial = 'EXHIBICION'
        ORDER BY id_vehiculo
        """
    )

    if not unidades_exhibicion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay unidades de exhibición habilitadas en este momento."
        )

    id_objetivo = datos.id_vehiculo or unidades_exhibicion[0]["id_vehiculo"]
    unidad_elegida = next((u for u in unidades_exhibicion if u["id_vehiculo"] == id_objetivo), None)
    if not unidad_elegida:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La unidad solicitada no es un vehículo de exhibición."
        )

    # Verificar que ningún otro invitado tenga una reserva activa sobre esta unidad física
    ocupadas = db_manager.execute_query(
        """
        SELECT id_sesion, nombre_operador,
               TIMESTAMPDIFF(SECOND, NOW(), expira_en) AS segundos_restantes
        FROM sesiones_control
        WHERE id_vehiculo = %s AND activa = 1 AND expira_en > NOW()
        LIMIT 1
        """,
        (id_objetivo,)
    )

    if ocupadas:
        seg = max(1, int(ocupadas[0].get("segundos_restantes") or 60))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La unidad de exhibición '{unidad_elegida['nombre']}' está siendo utilizada por otro visitante. Tiempo restante aproximado: {seg} s."
        )

    jti = secrets.token_hex(12)
    nombre_visitante = (datos.nombre_visitante or "Cliente Potencial").strip()

    db_manager.execute_write(
        """
        INSERT INTO sesiones_control (id_vehiculo, id_usuario, token_jti, nombre_operador, tipo_sesion, inicio_en, expira_en, activa)
        VALUES (%s, NULL, %s, %s, 'INVITADO', NOW(), DATE_ADD(NOW(), INTERVAL %s SECOND), 1)
        """,
        (id_objetivo, jti, nombre_visitante, GUEST_TTL_SECONDS)
    )

    token = create_access_token(
        {
            "id_usuario": None,
            "nombre": nombre_visitante,
            "email": "invitado@vehiculoiot.com",
            "rol": "INVITADO",
            "id_vehiculo_reservado": id_objetivo,
            "jti": jti
        },
        expires_sec=GUEST_TTL_SECONDS
    )

    ip_cliente = request.client.host if request.client else "API"
    registrar_auditoria(
        None, "INVITADO", "RESERVA_INVITADO", "vehiculos", id_objetivo,
        f"Sesión temporal de exhibición iniciada por '{nombre_visitante}' ({GUEST_TTL_SECONDS}s) en unidad #{id_objetivo}",
        ip_cliente
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": GUEST_TTL_SECONDS,
        "usuario": {
            "id_usuario": None,
            "nombre": nombre_visitante,
            "email": "invitado@vehiculoiot.com",
            "rol": "INVITADO",
            "nombre_rol": "Invitado (Prueba Temporal)"
        },
        "reserva": {
            "id_vehiculo": id_objetivo,
            "nombre_vehiculo": unidad_elegida["nombre"],
            "segundos_restantes": GUEST_TTL_SECONDS
        },
        "unidades": [unidad_elegida]
    }


@router.get("/me")
def obtener_perfil_actual(user: Dict[str, Any] = Depends(get_current_user)):
    """Devuelve la sesión vigente, rol, unidades permitidas y segundos restantes si es Invitado."""
    unidades = _obtener_unidades_permitidas(user.get("id_usuario"), user.get("rol"), user.get("id_vehiculo_reservado"))
    return {
        "usuario": {
            "id_usuario": user.get("id_usuario"),
            "nombre": user.get("nombre"),
            "email": user.get("email"),
            "rol": user.get("rol"),
            "id_vehiculo_reservado": user.get("id_vehiculo_reservado"),
            "segundos_restantes": user.get("segundos_restantes"),
            "tipo_sesion": user.get("tipo_sesion")
        },
        "unidades": unidades
    }


@router.post("/logout")
async def cerrar_sesion(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Cierra la sesión actual, libera cualquier reserva exclusiva en sesiones_control
    y, si era una sesión de Invitado, envía orden de Detener por seguridad física.
    """
    jti = user.get("jti")
    id_res = user.get("id_vehiculo_reservado")

    # Invalida el token: aunque alguien lo haya copiado, ya no sirve
    revocar_token(jti, user.get("exp"))

    if jti:
        db_manager.execute_write(
            "UPDATE sesiones_control SET activa = 0 WHERE token_jti = %s",
            (jti,)
        )
        try:
            db_manager.execute_write(
                "UPDATE solicitudes_invitado SET estado = 'FINALIZADA' WHERE token_jti = %s AND estado = 'APROBADA'",
                (jti,)
            )
        except Exception:
            pass

    # Si un invitado cierra sesión o expira su prueba, detenemos físicamente la unidad de exhibición
    if user.get("rol") == "INVITADO" and id_res:
        try:
            from app.routers.demos import active_demo_tasks
            tarea = active_demo_tasks.pop(int(id_res), None)
            if tarea:
                tarea.cancel()
        except Exception:
            pass
        try:
            cmds = db_manager.execute_query(
                "SELECT id_comando FROM comandos WHERE id_vehiculo = %s AND LOWER(nombre) = 'detener' LIMIT 1",
                (id_res,)
            )
            if cmds:
                id_stop = cmds[0]["id_comando"]
                estado_stop = EstadoVehiculoUpdate(id_vehiculo=id_res, id_comando=id_stop, conectado=True)
                actualizado = telemetria_service.actualizar_estado(estado_stop)
                await ws_manager.broadcast_json({"tipo_evento": "movimiento_individual", "vehiculo": id_res, "datos": jsonable_encoder(actualizado)})
        except Exception as e:
            print(f"[LOGOUT STOP WARN] {e}")

    registrar_auditoria(
        user.get("id_usuario"), user.get("rol", "DESCONOCIDO"), "LOGOUT", "sesiones_control", id_res,
        f"Cierre de sesión de {user.get('nombre')}"
    )
    return {"mensaje": "Sesión cerrada correctamente"}


# ---------------------------------------------------------------------------------------------
# PRÉSTAMO DEL VEHÍCULO FÍSICO A UN INVITADO (con aprobación del Administrador)
# 1) El visitante envía su solicitud y recibe un código secreto de seguimiento.
# 2) El Administrador la aprueba o rechaza desde su panel.
# 3) Al aprobarse, el visitante recibe (una sola vez) su token de 3 minutos con TODOS los comandos.
# ---------------------------------------------------------------------------------------------

def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256((codigo or "").encode("utf-8")).hexdigest()


def _expirar_solicitudes_viejas() -> None:
    db_manager.execute_write(
        """
        UPDATE solicitudes_invitado SET estado = 'EXPIRADA', resuelta_en = NOW()
        WHERE estado = 'PENDIENTE' AND creada_en <= NOW() - INTERVAL %s SECOND
        """,
        (SOLICITUD_PENDIENTE_TTL_SECONDS,)
    )


def _buscar_solicitud(codigo: str) -> Dict[str, Any]:
    _expirar_solicitudes_viejas()
    filas = db_manager.execute_query(
        """
        SELECT s.id_solicitud, s.id_vehiculo, s.nombre_visitante, s.estado, s.token_jti, s.token_entregado,
               s.id_sesion, s.creada_en, v.nombre AS nombre_vehiculo,
               TIMESTAMPDIFF(SECOND, NOW(), sc.expira_en) AS segundos_restantes,
               sc.activa AS sesion_activa
        FROM solicitudes_invitado s
        INNER JOIN vehiculos v ON v.id_vehiculo = s.id_vehiculo
        LEFT JOIN sesiones_control sc ON sc.id_sesion = s.id_sesion
        WHERE s.codigo_hash = %s
        LIMIT 1
        """,
        (_hash_codigo(codigo),)
    )
    if not filas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada.")
    return filas[0]


@router.post("/invitado/solicitud", status_code=status.HTTP_201_CREATED)
def solicitar_prestamo_fisico(datos: SolicitudPrestamoRequest, request: Request):
    """El visitante pide manejar el vehículo físico. Queda PENDIENTE hasta que el Admin responda."""
    _expirar_solicitudes_viejas()
    unidad = db_manager.execute_query(
        "SELECT id_vehiculo, nombre, activo FROM vehiculos WHERE id_vehiculo = %s LIMIT 1",
        (UNIDAD_FISICA_ID,)
    )
    if not unidad or not unidad[0].get("activo"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El vehículo físico no está disponible en este momento.")

    prestamo = obtener_prestamo_activo(UNIDAD_FISICA_ID)
    if prestamo:
        seg = max(1, int(prestamo.get("segundos_restantes") or 1))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Otro visitante está manejando el vehículo físico. Intenta de nuevo en {seg} s."
        )

    pendientes = db_manager.execute_query("SELECT COUNT(*) AS n FROM solicitudes_invitado WHERE estado = 'PENDIENTE'")
    if pendientes and int(pendientes[0]["n"]) >= MAX_SOLICITUDES_PENDIENTES:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Hay demasiadas solicitudes en espera. Intenta más tarde.")

    nombre = (datos.nombre_visitante or "Visitante").strip() or "Visitante"
    codigo = secrets.token_urlsafe(24)
    ip_cliente = request.client.host if request.client else "API"
    res = db_manager.execute_write(
        """
        INSERT INTO solicitudes_invitado (id_vehiculo, nombre_visitante, codigo_hash, estado, ip_origen)
        VALUES (%s, %s, %s, 'PENDIENTE', %s)
        """,
        (UNIDAD_FISICA_ID, nombre, _hash_codigo(codigo), ip_cliente)
    )
    registrar_auditoria(
        None, "INVITADO", "SOLICITUD_PRESTAMO", "solicitudes_invitado", res.get("lastrowid"),
        f"'{nombre}' solicitó manejar el vehículo físico (unidad #{UNIDAD_FISICA_ID})", ip_cliente
    )
    return {
        "id_solicitud": res.get("lastrowid"),
        "codigo": codigo,
        "estado": "PENDIENTE",
        "nombre_vehiculo": unidad[0]["nombre"],
        "espera_max_seg": SOLICITUD_PENDIENTE_TTL_SECONDS
    }


@router.get("/invitado/solicitud/{codigo}")
def consultar_solicitud(codigo: str):
    """
    El visitante consulta su solicitud. Cuando el Admin la aprueba, la PRIMERA consulta entrega
    el token de 3 minutos; las siguientes ya no lo vuelven a entregar.
    """
    sol = _buscar_solicitud(codigo)
    estado = sol["estado"]
    if estado != "APROBADA":
        return {"estado": estado, "nombre_vehiculo": sol["nombre_vehiculo"]}

    if not sol.get("sesion_activa") or int(sol.get("segundos_restantes") or 0) <= 0:
        return {"estado": "FINALIZADA", "nombre_vehiculo": sol["nombre_vehiculo"]}

    marcado = db_manager.execute_write(
        "UPDATE solicitudes_invitado SET token_entregado = 1 WHERE id_solicitud = %s AND token_entregado = 0",
        (sol["id_solicitud"],)
    )
    if not marcado.get("rowcount"):
        return {"estado": "APROBADA", "token_entregado": True, "nombre_vehiculo": sol["nombre_vehiculo"],
                "detalle": "El acceso ya se entregó a este navegador."}

    seg = int(sol["segundos_restantes"])
    token = create_access_token(
        {
            "id_usuario": None,
            "nombre": sol["nombre_visitante"],
            "email": "invitado@vehiculoiot.com",
            "rol": "INVITADO",
            "id_vehiculo_reservado": sol["id_vehiculo"],
            "jti": sol["token_jti"]
        },
        expires_sec=seg
    )
    return {
        "estado": "APROBADA",
        "access_token": token,
        "token_type": "bearer",
        "expires_in": seg,
        "usuario": {
            "id_usuario": None,
            "nombre": sol["nombre_visitante"],
            "email": "invitado@vehiculoiot.com",
            "rol": "INVITADO",
            "nombre_rol": "Invitado (Vehículo físico)",
            "tipo_sesion": TIPO_PRESTAMO_FISICO
        },
        "reserva": {
            "id_vehiculo": sol["id_vehiculo"],
            "nombre_vehiculo": sol["nombre_vehiculo"],
            "segundos_restantes": seg,
            "tipo_sesion": TIPO_PRESTAMO_FISICO
        }
    }


@router.delete("/invitado/solicitud/{codigo}")
def cancelar_solicitud(codigo: str):
    """El visitante retira su solicitud mientras sigue PENDIENTE."""
    sol = _buscar_solicitud(codigo)
    if sol["estado"] != "PENDIENTE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"La solicitud ya está {sol['estado']}.")
    db_manager.execute_write(
        "UPDATE solicitudes_invitado SET estado = 'CANCELADA', resuelta_en = NOW() WHERE id_solicitud = %s AND estado = 'PENDIENTE'",
        (sol["id_solicitud"],)
    )
    return {"estado": "CANCELADA"}
