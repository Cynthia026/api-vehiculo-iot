import os
import hmac
import json
import time
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.database import db_manager

# Clave secreta para firma HMAC-SHA256 de JWT (configurable en .env)
JWT_SECRET = os.getenv("JWT_SECRET", "vehiculo-iot-super-secret-key-2026-rds")
DEFAULT_SALT = "iot2026"
TOKEN_TTL_SECONDS = 60 * 60 * 8      # 8 horas para Admin / Usuario
GUEST_TTL_SECONDS = 60 * 3           # 3 minutos para sesión temporal de Invitado

security_scheme = HTTPBearer(auto_error=False)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(plain_password: str, salt: str = DEFAULT_SALT) -> str:
    """Genera hash con formato sha256$<salt>$<hex> compatible con SHA2 de MySQL."""
    digest = hashlib.sha256(f"{salt}:{plain_password}".encode("utf-8")).hexdigest().lower()
    return f"sha256${salt}${digest}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verifica contraseña en formato sha256$<salt>$<hex> de forma resistente a timing attacks."""
    if not stored_hash:
        return False
    parts = stored_hash.split("$")
    if len(parts) == 3 and parts[0] == "sha256":
        salt = parts[1]
        expected = hash_password(plain_password, salt)
        return hmac.compare_digest(expected, stored_hash.lower())
    return hmac.compare_digest(plain_password, stored_hash)


def create_access_token(payload: Dict[str, Any], expires_sec: int = TOKEN_TTL_SECONDS) -> str:
    """Crea un JWT estándar HS256 usando únicamente la librería estándar de Python."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = {
        **payload,
        "iat": now,
        "exp": now + expires_sec,
        "jti": payload.get("jti") or secrets.token_hex(12)
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    body_b64 = _b64url_encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{body_b64}".encode("utf-8")
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{body_b64}.{sig_b64}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """Valida firma y expiración de un JWT HS256."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Formato de token inválido")
        header_b64, body_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{body_b64}".encode("utf-8")
        expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Firma de token inválida")
        payload = json.loads(_b64url_decode(body_b64).decode("utf-8"))
        if int(time.time()) > int(payload.get("exp", 0)):
            raise ValueError("La sesión ha expirado")
        return payload
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o corrupto")


def registrar_auditoria(
    id_usuario: Optional[int],
    rol: str,
    accion: str,
    entidad: str,
    id_recurso: Optional[int] = None,
    detalle: Optional[str] = None,
    ip_origen: Optional[str] = None
):
    """Inserta un evento en bitacora_auditoria sin interrumpir el flujo si la tabla aún no fue migrada."""
    try:
        db_manager.execute_write(
            """
            INSERT INTO bitacora_auditoria (id_usuario, rol, accion, entidad, id_recurso, detalle, ip_origen)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (id_usuario, rol, accion, entidad, id_recurso, detalle, ip_origen or "API")
        )
    except Exception as e:
        print(f"[AUDITORIA WARN] No se pudo registrar evento ({accion}): {e}")


def limpiar_sesiones_expiradas():
    """Marca como inactivas las reservas de sesión cuyo tiempo límite ya venció."""
    try:
        db_manager.execute_write(
            "UPDATE sesiones_control SET activa = 0 WHERE activa = 1 AND expira_en <= NOW()"
        )
        db_manager.execute_write(
            """
            UPDATE vehiculos
            SET soporte_autorizado = 0, soporte_expira_en = NULL
            WHERE soporte_autorizado = 1 AND soporte_expira_en IS NOT NULL AND soporte_expira_en <= NOW()
            """
        )
    except Exception:
        pass


def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
) -> Optional[Dict[str, Any]]:
    """Extrae el usuario autenticado si se envió Authorization: Bearer <token> o ?token=."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "token" in request.query_params:
        token = request.query_params.get("token")

    if not token:
        return None

    payload = decode_access_token(token)
    limpiar_sesiones_expiradas()

    # Si es sesión de invitado, verificar que su reserva siga activa en BD
    if payload.get("rol") == "INVITADO" and payload.get("jti"):
        try:
            sesiones = db_manager.execute_query(
                """
                SELECT id_sesion, id_vehiculo, expira_en, activa,
                       TIMESTAMPDIFF(SECOND, NOW(), expira_en) AS segundos_restantes
                FROM sesiones_control
                WHERE token_jti = %s LIMIT 1
                """,
                (payload["jti"],)
            )
            if not sesiones or not sesiones[0].get("activa") or (sesiones[0].get("segundos_restantes") or 0) <= 0:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="La sesión temporal de demostración para Invitado ha finalizado."
                )
            payload["id_vehiculo_reservado"] = sesiones[0]["id_vehiculo"]
            payload["segundos_restantes"] = max(0, int(sesiones[0]["segundos_restantes"]))
        except HTTPException:
            raise
        except Exception:
            pass

    return payload


def get_current_user(
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
) -> Dict[str, Any]:
    """Exige sesión autenticada válida (401 si no hay token)."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Inicia sesión para continuar."
        )
    return user


def require_roles(*allowed_roles: str):
    """Genera una dependencia FastAPI que exige uno de los roles indicados (RBAC)."""
    def _checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("rol") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado para el rol '{user.get('rol')}'. Se requiere: {', '.join(allowed_roles)}"
            )
        return user
    return _checker


def verificar_acceso_vehiculo(
    id_vehiculo: int,
    user: Optional[Dict[str, Any]],
    modo: str = "lectura"
) -> Dict[str, Any]:
    """
    Autorización por Recurso (anti-BOLA / anti-IDOR):
    - modo='lectura': consultar estado, historial, comandos o demos del vehículo.
    - modo='control': enviar comandos de movimiento, iniciar/cancelar demos o editar demos propias.
    - modo='admin': editar inventario o configuración administrativa.
    """
    limpiar_sesiones_expiradas()

    # Consultar metadatos comerciales de la unidad física
    try:
        filas = db_manager.execute_query(
            """
            SELECT v.id_vehiculo, v.nombre, v.modelo, v.activo,
                   COALESCE(v.estado_comercial, 'DISPONIBLE') AS estado_comercial,
                   COALESCE(v.soporte_autorizado, 0) AS soporte_autorizado,
                   v.soporte_expira_en,
                   a.id_usuario AS id_propietario,
                   u.nombre AS nombre_propietario
            FROM vehiculos v
            LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
            LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
            WHERE v.id_vehiculo = %s
            LIMIT 1
            """,
            (id_vehiculo,)
        )
    except Exception:
        # Fallback si la migración V001 aún no ha sido ejecutada en RDS
        filas = db_manager.execute_sp("sp_obtener_vehiculo", (id_vehiculo,))
        if not filas:
            raise HTTPException(status_code=404, detail=f"Vehículo {id_vehiculo} no encontrado")
        return filas[0]

    if not filas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Vehículo {id_vehiculo} no encontrado")

    unidad = filas[0]

    # Si no se envió token (modo compatibilidad 4.1/4.2 cuando no se ha iniciado sesión en clientes antiguos):
    # En 4.3 el frontend siempre envía el token Bearer del rol activo.
    if not user:
        return unidad

    rol = user.get("rol")
    id_usuario = user.get("id_usuario")
    estado_com = unidad.get("estado_comercial", "DISPONIBLE")
    id_propietario = unidad.get("id_propietario")

    # 1. REGLAS PARA ROL USUARIO (COMPRADOR)
    if rol == "USUARIO":
        if id_propietario != id_usuario:
            registrar_auditoria(
                id_usuario, rol, "ACCESO_CRUZADO_BLOQUEADO", "vehiculos", id_vehiculo,
                f"Intento BOLA/IDOR bloqueado en modo '{modo}' sobre unidad {id_vehiculo}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: la unidad #{id_vehiculo} no está asignada a tu cuenta."
            )
        return unidad

    # 2. REGLAS PARA ROL INVITADO (CLIENTE POTENCIAL)
    if rol == "INVITADO":
        if estado_com != "EXHIBICION":
            registrar_auditoria(
                id_usuario, rol, "INVITADO_UNIDAD_PRIVADA_BLOQUEADO", "vehiculos", id_vehiculo,
                f"Invitado intentó acceder a unidad {id_vehiculo} ({estado_com})"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso restringido: el perfil Invitado sólo puede utilizar unidades de EXHIBICIÓN."
            )
        if modo == "control":
            id_res = user.get("id_vehiculo_reservado")
            if id_res and int(id_res) != int(id_vehiculo):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Tu sesión de exhibición sólo tiene reservada la unidad #{id_res}."
                )
        return unidad

    # 3. REGLAS PARA ROL ADMIN (EMPRESA)
    if rol == "ADMIN":
        if modo == "control" and estado_com == "VENDIDO" and id_propietario is not None:
            if not unidad.get("soporte_autorizado"):
                registrar_auditoria(
                    id_usuario, rol, "ADMIN_CONTROL_SIN_SOPORTE_BLOQUEADO", "vehiculos", id_vehiculo,
                    f"Admin intentó operar unidad vendida #{id_vehiculo} sin consentimiento del propietario"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Control privado protegido: esta unidad pertenece a un cliente comprador. Solicita al propietario activar 'Autorización de Soporte Técnico' desde Mis Vehículos."
                )
        return unidad

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado")
