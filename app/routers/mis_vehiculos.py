from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any, List
from app.database import db_manager
from app.security import (
    get_current_user,
    require_roles,
    verificar_acceso_vehiculo,
    registrar_auditoria,
    limpiar_sesiones_expiradas
)
from app.schemas.administracion import SoporteToggleRequest

router = APIRouter(prefix="/api", tags=["Mis Vehículos y Catálogo Exhibición (4.3)"])


@router.get("/mis-vehiculos")
def obtener_mis_vehiculos(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Devuelve las unidades a las que tiene acceso el usuario autenticado:
    - USUARIO: exclusivamente las unidades asignadas a su cuenta.
    - INVITADO: la unidad de exhibición reservada en su sesión temporal.
    - ADMIN: todas las unidades registradas en el inventario.
    """
    limpiar_sesiones_expiradas()
    rol = user.get("rol")
    id_usuario = user.get("id_usuario")

    if rol == "USUARIO":
        return db_manager.execute_query(
            """
            SELECT v.id_vehiculo, v.nombre, v.modelo, v.descripcion, v.microcontrolador,
                   COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
                   COALESCE(v.estado_comercial, 'VENDIDO') AS estado_comercial,
                   COALESCE(v.soporte_autorizado, 0) AS soporte_autorizado,
                   v.soporte_expira_en,
                   a.fecha_asignacion,
                   ev.conectado,
                   c.nombre AS ultimo_comando,
                   ev.fecha_actualizacion
            FROM vehiculos v
            INNER JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
            LEFT JOIN estado_vehiculo ev ON ev.id_vehiculo = v.id_vehiculo
            LEFT JOIN comandos c ON c.id_comando = ev.id_comando
            WHERE a.id_usuario = %s AND v.activo = 1
            ORDER BY v.id_vehiculo
            """,
            (id_usuario,)
        )

    if rol == "INVITADO":
        return db_manager.execute_query(
            """
            SELECT v.id_vehiculo, v.nombre, v.modelo, v.descripcion, v.microcontrolador,
                   COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
                   v.estado_comercial,
                   s.tipo_sesion,
                   ev.conectado,
                   c.nombre AS ultimo_comando,
                   ev.fecha_actualizacion
            FROM vehiculos v
            LEFT JOIN estado_vehiculo ev ON ev.id_vehiculo = v.id_vehiculo
            LEFT JOIN comandos c ON c.id_comando = ev.id_comando
            LEFT JOIN sesiones_control s ON s.token_jti = %s
            WHERE v.activo = 1 AND v.id_vehiculo = %s
            ORDER BY v.id_vehiculo
            """,
            (user.get("jti") or "", user.get("id_vehiculo_reservado") or 0)
        )

    # ADMIN
    return db_manager.execute_query(
        """
        SELECT v.id_vehiculo, v.nombre, v.modelo, v.descripcion, v.microcontrolador,
               COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
               COALESCE(v.estado_comercial, 'DISPONIBLE') AS estado_comercial,
               COALESCE(v.soporte_autorizado, 0) AS soporte_autorizado,
               v.soporte_expira_en,
               u.nombre AS nombre_propietario,
               ev.conectado,
               c.nombre AS ultimo_comando,
               ev.fecha_actualizacion
        FROM vehiculos v
        LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
        LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
        LEFT JOIN estado_vehiculo ev ON ev.id_vehiculo = v.id_vehiculo
        LEFT JOIN comandos c ON c.id_comando = ev.id_comando
        WHERE v.activo = 1
        ORDER BY v.id_vehiculo
        """
    )


@router.patch("/mis-vehiculos/{id_vehiculo}/soporte")
def configurar_autorizacion_soporte(
    id_vehiculo: int,
    datos: SoporteToggleRequest,
    user: Dict[str, Any] = Depends(require_roles("USUARIO"))
):
    """
    Permite exclusivamente al comprador propietario de la unidad otorgar o revocar
    el permiso temporal de soporte técnico para que el Administrador pueda operar su vehículo.
    """
    verificar_acceso_vehiculo(id_vehiculo, user, modo="control")

    if datos.autorizado:
        db_manager.execute_write(
            """
            UPDATE vehiculos
            SET soporte_autorizado = 1,
                soporte_expira_en = DATE_ADD(NOW(), INTERVAL %s MINUTE)
            WHERE id_vehiculo = %s
            """,
            (datos.minutos, id_vehiculo)
        )
        detalle = f"Propietario autorizó soporte técnico para Admin por {datos.minutos} min en unidad #{id_vehiculo}"
    else:
        db_manager.execute_write(
            """
            UPDATE vehiculos
            SET soporte_autorizado = 0,
                soporte_expira_en = NULL
            WHERE id_vehiculo = %s
            """,
            (id_vehiculo,)
        )
        detalle = f"Propietario revocó autorización de soporte técnico en unidad #{id_vehiculo}"

    registrar_auditoria(
        user["id_usuario"], "USUARIO", "SOPORTE_AUTORIZACION", "vehiculos", id_vehiculo, detalle
    )

    actualizado = db_manager.execute_query(
        "SELECT id_vehiculo, soporte_autorizado, soporte_expira_en FROM vehiculos WHERE id_vehiculo = %s",
        (id_vehiculo,)
    )
    return {
        "mensaje": detalle,
        "vehiculo": actualizado[0] if actualizado else {"id_vehiculo": id_vehiculo, "soporte_autorizado": int(datos.autorizado)}
    }


@router.get("/exhibicion/catalogo")
def obtener_catalogo_publico():
    """
    Endpoint público para que visitantes e Invitados consulten el catálogo de modelos comerciales
    y verifiquen qué unidades de exhibición están libres u ocupadas.
    """
    limpiar_sesiones_expiradas()

    modelos = db_manager.execute_query(
        "SELECT * FROM modelos_catalogo WHERE activo = 1 ORDER BY id_modelo"
    )
    unidades_exhibicion = db_manager.execute_query(
        """
        SELECT v.id_vehiculo, v.nombre, v.modelo, v.descripcion, v.microcontrolador,
               COALESCE(v.numero_serie, CONCAT('SN-00', v.id_vehiculo)) AS numero_serie,
               s.id_sesion AS sesion_activa,
               s.nombre_operador,
               TIMESTAMPDIFF(SECOND, NOW(), s.expira_en) AS segundos_ocupado
        FROM vehiculos v
        LEFT JOIN sesiones_control s ON s.id_vehiculo = v.id_vehiculo AND s.activa = 1 AND s.expira_en > NOW()
        WHERE v.activo = 1 AND v.estado_comercial = 'EXHIBICION'
        ORDER BY v.id_vehiculo
        """
    )
    return {
        "modelos": modelos,
        "unidades_exhibicion": unidades_exhibicion
    }
