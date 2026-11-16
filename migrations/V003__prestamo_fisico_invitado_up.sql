-- =====================================================================
-- V003 · Préstamo del vehículo físico a un Invitado con aprobación del Admin
-- ---------------------------------------------------------------------
-- ANTES DE EJECUTAR: respaldo de la base de datos, por ejemplo:
--   mysqldump -h <endpoint-rds> -u <usuario> -p --single-transaction \
--             --routines --triggers vehiculo_iot > respaldo_antes_V003.sql
-- El servidor FastAPI también aplica este cambio de forma idempotente
-- al arrancar (database.ensure_schema_4_3).
-- =====================================================================

-- Cada solicitud de un visitante para manejar el vehículo físico.
-- El código de seguimiento se guarda como hash SHA-256 (nunca en claro).
-- Al aprobarse se crea una fila en sesiones_control con tipo_sesion = 'PRESTAMO_FISICO'.
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

-- Verificación
SELECT COUNT(*) AS solicitudes FROM solicitudes_invitado;
