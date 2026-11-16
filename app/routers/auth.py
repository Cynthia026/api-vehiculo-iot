import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.encoders import jsonable_encoder
from typing import Dict, Any, Optional
from app.database import db_manager
from app.schemas.administracion import LoginRequest, GuestSessionRequest
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
    GUEST_TTL_SECONDS
)
from app.services.telemetria_service import telemetria_service
from app.schemas.estado import EstadoVehiculoUpdate
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/api/auth", tags=["Autenticación y Sesiones (4.3)"])


def _obtener_unidades_permitidas(id_usuario: int, rol: str):
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
    unidades = _obtener_unidades_permitidas(user.get("id_usuario"), user.get("rol"))
    return {
        "usuario": {
            "id_usuario": user.get("id_usuario"),
            "nombre": user.get("nombre"),
            "email": user.get("email"),
            "rol": user.get("rol"),
            "id_vehiculo_reservado": user.get("id_vehiculo_reservado"),
            "segundos_restantes": user.get("segundos_restantes")
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

    # Si un invitado cierra sesión o expira su prueba, detenemos físicamente la unidad de exhibición
    if user.get("rol") == "INVITADO" and id_res:
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
