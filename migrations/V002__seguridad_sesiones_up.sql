-- =====================================================================
-- V002 · Seguridad de sesiones y baja lógica (Práctica 4.3)
-- ---------------------------------------------------------------------
-- ANTES DE EJECUTAR: respaldo de la base de datos, por ejemplo:
--   mysqldump -h <endpoint-rds> -u <usuario> -p --single-transaction \
--             --routines --triggers vehiculo_iot > respaldo_antes_V002.sql
-- DDL en MySQL hace COMMIT implícito: no confíes en ROLLBACK, usa el
-- script V002__seguridad_sesiones_down.sql para revertir.
-- El servidor FastAPI también aplica este cambio de forma idempotente
-- al arrancar (database.ensure_schema_4_3).
-- =====================================================================

-- 1) Tokens invalidados por logout (rechazo inmediato aunque la firma sea válida)
CREATE TABLE IF NOT EXISTS tokens_revocados (
    jti VARCHAR(80) PRIMARY KEY,
    expira_en DATETIME NOT NULL,
    fecha_revocacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tokens_revocados_expira (expira_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) Baja lógica de unidades: nuevo valor de estado_comercial 'INACTIVO'
--    (la columna es VARCHAR(30), no requiere ALTER). Verificación:
SELECT estado_comercial, COUNT(*) AS total FROM vehiculos GROUP BY estado_comercial;

-- 3) Rotación de contraseñas de demostración publicadas en V001:
--    NO se hace con SQL (no deben quedar contraseñas en el repositorio).
--    Define SEED_ADMIN_PASSWORD, SEED_CYNTHIA_PASSWORD, SEED_CARLOS_PASSWORD
--    y SEED_INVITADO_PASSWORD en el .env del servidor y reinicia la API.
