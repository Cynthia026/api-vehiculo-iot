import os
import secrets
import hashlib
import pymysql
from pymysql.cursors import DictCursor
from typing import List, Optional, Any
from app.config import settings

class DatabaseManager:
    """
    Clase encargada de administrar la conexión a Amazon RDS,
    estandarizar la ejecución de los 21 Stored Procedures y
    ejecutar consultas parametrizadas seguras para Administración (4.3).
    """
    def __init__(self):
        self._host = settings.DB_HOST
        self._port = settings.DB_PORT
        self._user = settings.DB_USER
        self._password = settings.DB_PASSWORD
        self._database = settings.DB_NAME

    def get_connection(self):
        """Retorna una conexión activa hacia Amazon RDS."""
        return pymysql.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
            cursorclass=DictCursor,
            autocommit=True
        )

    def test_connection(self) -> bool:
        """Comprueba conectividad activa con Amazon RDS."""
        try:
            connection = self.get_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS status;")
                result = cursor.fetchone()
            connection.close()
            return result is not None and result.get("status") == 1
        except Exception as error:
            print(f"[ERROR RDS] Conexión fallida: {error}")
            return False

    def execute_sp(self, procedure_name: str, params: Optional[tuple] = None) -> List[dict]:
        """
        Ejecuta un procedimiento almacenado vía CALL y retorna los registros.
        """
        connection = self.get_connection()
        try:
            with connection.cursor() as cursor:
                if params:
                    cursor.callproc(procedure_name, params)
                else:
                    cursor.callproc(procedure_name)
                result = cursor.fetchall()
                return list(result)
        finally:
            connection.close()

    def execute_query(self, sql: str, params: Optional[tuple] = None) -> List[dict]:
        """
        Ejecuta una consulta SELECT parametrizada (%s) y retorna la lista de diccionarios.
        """
        connection = self.get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params or ())
                result = cursor.fetchall()
                return list(result)
        finally:
            connection.close()

    def execute_write(self, sql: str, params: Optional[tuple] = None) -> dict:
        """
        Ejecuta una sentencia INSERT, UPDATE o DELETE parametrizada (%s)
        y retorna {'lastrowid': ..., 'rowcount': ...}.
        """
        connection = self.get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params or ())
                return {
                    "lastrowid": cursor.lastrowid,
                    "rowcount": cursor.rowcount
                }
        finally:
            connection.close()

    def _add_column_if_missing(self, cursor, table_name: str, column_name: str, definition: str):
        cursor.execute(
            """
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (table_name, column_name)
        )
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def ensure_schema_4_3(self) -> bool:
        """
        Aplica de forma idempotente y no destructiva las tablas y columnas
        de la Práctica 4.3 (Administración) en Amazon RDS al iniciar el servidor.
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS roles (
                        id_rol INT AUTO_INCREMENT PRIMARY KEY,
                        codigo VARCHAR(30) NOT NULL UNIQUE,
                        nombre VARCHAR(60) NOT NULL,
                        descripcion VARCHAR(255) NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS usuarios (
                        id_usuario INT AUTO_INCREMENT PRIMARY KEY,
                        id_rol INT NOT NULL,
                        nombre VARCHAR(100) NOT NULL,
                        email VARCHAR(120) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        activo TINYINT(1) NOT NULL DEFAULT 1,
                        fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT fk_usuarios_rol FOREIGN KEY (id_rol) REFERENCES roles(id_rol)
                            ON UPDATE CASCADE ON DELETE RESTRICT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS modelos_catalogo (
                        id_modelo INT AUTO_INCREMENT PRIMARY KEY,
                        codigo_modelo VARCHAR(40) NOT NULL UNIQUE,
                        nombre VARCHAR(80) NOT NULL,
                        descripcion VARCHAR(255) NULL,
                        microcontrolador_default VARCHAR(50) NOT NULL DEFAULT 'ESP8266',
                        tiene_brazo TINYINT(1) NOT NULL DEFAULT 1,
                        tiene_motores_giro TINYINT(1) NOT NULL DEFAULT 1,
                        activo TINYINT(1) NOT NULL DEFAULT 1,
                        fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS asignaciones_vehiculo (
                        id_asignacion INT AUTO_INCREMENT PRIMARY KEY,
                        id_vehiculo INT NOT NULL,
                        id_usuario INT NOT NULL,
                        fecha_asignacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        notas VARCHAR(255) NULL,
                        activo TINYINT(1) NOT NULL DEFAULT 1,
                        CONSTRAINT fk_asig_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
                            ON UPDATE CASCADE ON DELETE RESTRICT,
                        CONSTRAINT fk_asig_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
                            ON UPDATE CASCADE ON DELETE RESTRICT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sesiones_control (
                        id_sesion INT AUTO_INCREMENT PRIMARY KEY,
                        id_vehiculo INT NOT NULL,
                        id_usuario INT NULL,
                        token_jti VARCHAR(80) NOT NULL UNIQUE,
                        nombre_operador VARCHAR(100) NULL,
                        tipo_sesion VARCHAR(30) NOT NULL DEFAULT 'INVITADO',
                        inicio_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        expira_en DATETIME NOT NULL,
                        activa TINYINT(1) NOT NULL DEFAULT 1,
                        CONSTRAINT fk_sesion_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
                            ON UPDATE CASCADE ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bitacora_auditoria (
                        id_auditoria BIGINT AUTO_INCREMENT PRIMARY KEY,
                        id_usuario INT NULL,
                        rol VARCHAR(30) NOT NULL,
                        accion VARCHAR(60) NOT NULL,
                        entidad VARCHAR(50) NOT NULL,
                        id_recurso INT NULL,
                        detalle VARCHAR(500) NULL,
                        ip_origen VARCHAR(60) NULL,
                        fecha_hora TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                # Columnas aditivas en vehiculos y demos
                self._add_column_if_missing(cur, "vehiculos", "id_modelo", "INT NULL")
                self._add_column_if_missing(cur, "vehiculos", "numero_serie", "VARCHAR(60) NULL UNIQUE")
                self._add_column_if_missing(cur, "vehiculos", "estado_comercial", "VARCHAR(30) NOT NULL DEFAULT 'DISPONIBLE'")
                self._add_column_if_missing(cur, "vehiculos", "soporte_autorizado", "TINYINT(1) NOT NULL DEFAULT 0")
                self._add_column_if_missing(cur, "vehiculos", "soporte_expira_en", "DATETIME NULL")

                self._add_column_if_missing(cur, "demos", "id_usuario_creador", "INT NULL")
                self._add_column_if_missing(cur, "demos", "tipo_demo", "VARCHAR(20) NOT NULL DEFAULT 'EMPRESA'")
                self._add_column_if_missing(cur, "demos", "duracion_max_seg", "INT NOT NULL DEFAULT 60")

                # V002: tokens invalidados por logout (sesiones cerradas antes de expirar)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tokens_revocados (
                        jti VARCHAR(80) PRIMARY KEY,
                        expira_en DATETIME NOT NULL,
                        fecha_revocacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_tokens_revocados_expira (expira_en)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                cur.execute("DELETE FROM tokens_revocados WHERE expira_en < NOW() - INTERVAL 1 DAY")

                # V003: solicitudes de Invitado para manejar el vehículo físico (aprobación del Admin)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS solicitudes_invitado (
                        id_solicitud INT AUTO_INCREMENT PRIMARY KEY,
                        id_vehiculo INT NOT NULL,
                        nombre_visitante VARCHAR(100) NOT NULL,
                        codigo_hash CHAR(64) NOT NULL,
                        estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
                            COMMENT 'PENDIENTE | APROBADA | RECHAZADA | CANCELADA | EXPIRADA | FINALIZADA',
                        ip_origen VARCHAR(64) NULL,
                        creada_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        resuelta_en DATETIME NULL,
                        id_admin INT NULL,
                        id_sesion INT NULL,
                        token_jti VARCHAR(80) NULL,
                        token_entregado TINYINT(1) NOT NULL DEFAULT 0,
                        UNIQUE KEY uq_solicitud_codigo (codigo_hash),
                        INDEX idx_solicitud_estado (estado, creada_en),
                        CONSTRAINT fk_solicitud_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
                            ON UPDATE CASCADE ON DELETE CASCADE,
                        CONSTRAINT fk_solicitud_admin FOREIGN KEY (id_admin) REFERENCES usuarios(id_usuario)
                            ON UPDATE CASCADE ON DELETE SET NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                # Datos semilla idempotentes
                cur.execute("""
                    INSERT INTO roles (id_rol, codigo, nombre, descripcion) VALUES
                        (1, 'ADMIN', 'Administrador', 'Empresa propietaria'),
                        (2, 'USUARIO', 'Usuario Comprador', 'Cliente propietario de unidades'),
                        (3, 'INVITADO', 'Invitado', 'Cliente potencial en prueba temporal')
                    ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);
                """)
                cur.execute("""
                    INSERT INTO modelos_catalogo (id_modelo, codigo_modelo, nombre, descripcion, microcontrolador_default, tiene_brazo, tiene_motores_giro, activo) VALUES
                        (1, 'EXC-IOT-V1', 'Excavadora IoT', 'Vehículo oruga con brazo hidráulico articulado y giro de cabina.', 'ESP8266', 1, 1, 1),
                        (2, 'ROV-IOT-V1', 'Rover Explorador IoT', 'Vehículo compacto 4WD con tracción diferencial y telemetría.', 'ESP8266', 0, 1, 1)
                    ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);
                """)
                # Cuentas de demostración. Las contraseñas NUNCA van en el código:
                # se leen de .env (SEED_*_PASSWORD). Si una variable no existe, la cuenta se crea
                # (sólo si no existía) con una contraseña aleatoria desconocida, y NUNCA se
                # sobrescribe una contraseña existente salvo que definas la variable (rotación).
                cuentas = [
                    (1, 1, "Administrador General", "admin@vehiculoiot.com", "SEED_ADMIN_PASSWORD"),
                    (2, 2, "Cynthia Martínez García", "cynthia@cliente.com", "SEED_CYNTHIA_PASSWORD"),
                    (3, 2, "Carlos Mendoza (Comprador B)", "carlos@cliente.com", "SEED_CARLOS_PASSWORD"),
                    (4, 3, "Invitado Demo", "invitado@vehiculoiot.com", "SEED_INVITADO_PASSWORD"),
                ]
                for id_u, id_rol, nombre, email, var in cuentas:
                    clave = os.getenv(var, "").strip()
                    sal = secrets.token_hex(8)
                    if clave:
                        hash_pwd = f"sha256${sal}${hashlib.sha256(f'{sal}:{clave}'.encode('utf-8')).hexdigest()}"
                        cur.execute(
                            """
                            INSERT INTO usuarios (id_usuario, id_rol, nombre, email, password_hash, activo)
                            VALUES (%s, %s, %s, %s, %s, 1)
                            ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash)
                            """,
                            (id_u, id_rol, nombre, email, hash_pwd)
                        )
                    else:
                        aleatoria = secrets.token_urlsafe(24)
                        hash_pwd = f"sha256${sal}${hashlib.sha256(f'{sal}:{aleatoria}'.encode('utf-8')).hexdigest()}"
                        cur.execute(
                            "INSERT IGNORE INTO usuarios (id_usuario, id_rol, nombre, email, password_hash, activo) VALUES (%s, %s, %s, %s, %s, 1)",
                            (id_u, id_rol, nombre, email, hash_pwd)
                        )

                # Asignación inicial de la Unidad 1 SÓLO la primera vez (tabla vacía).
                # Antes se ejecutaba en cada arranque y deshacía las liberaciones/reasignaciones del Admin.
                cur.execute("SELECT COUNT(*) AS total FROM asignaciones_vehiculo")
                primera_vez = (cur.fetchone() or {}).get("total", 0) == 0
                cur.execute("""
                    UPDATE vehiculos
                    SET id_modelo = COALESCE(id_modelo, 1),
                        numero_serie = COALESCE(numero_serie, 'SN-EXC-0001')
                    WHERE id_vehiculo = 1;
                """)
                if primera_vez:
                    cur.execute("""
                        UPDATE vehiculos SET estado_comercial = 'VENDIDO'
                        WHERE id_vehiculo = 1 AND estado_comercial = 'DISPONIBLE';
                    """)
                    cur.execute("""
                        INSERT INTO asignaciones_vehiculo (id_vehiculo, id_usuario, notas, activo)
                        SELECT 1, 2, 'Asignación titular de Unidad 1 a Cynthia Martínez García', 1
                        WHERE EXISTS (SELECT 1 FROM vehiculos WHERE id_vehiculo = 1);
                    """)
            conn.close()
            return True
        except Exception as err:
            print(f"[MIGRACION 4.3 WARN] {err}")
            return False

# Singleton para consumo de los servicios
db_manager = DatabaseManager()
