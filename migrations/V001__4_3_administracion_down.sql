-- ============================================================================
-- ARCHIVO: V001__4_3_administracion_down.sql
-- PROPÓSITO: Script de reversión controlada para entornos de prueba.
--            Elimina las tablas y columnas añadidas en V001 conservando
--            intactos los datos originales de la Unidad 1 (4.1 y 4.2).
-- ============================================================================

USE vehiculo_iot;

-- 1. Eliminar tablas nuevas en orden inverso de dependencias FK
DROP TABLE IF EXISTS bitacora_auditoria;
DROP TABLE IF EXISTS sesiones_control;
DROP TABLE IF EXISTS asignaciones_vehiculo;
DROP TABLE IF EXISTS modelos_catalogo;
DROP TABLE IF EXISTS usuarios;
DROP TABLE IF EXISTS roles;

-- 2. Procedimiento auxiliar para eliminar columnas añadidas sólo si existen
DROP PROCEDURE IF EXISTS sp_mig_drop_column_if_exists;
DELIMITER $$
CREATE PROCEDURE sp_mig_drop_column_if_exists(
    IN p_table VARCHAR(64),
    IN p_column VARCHAR(64)
)
BEGIN
    IF EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table
          AND COLUMN_NAME = p_column
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE ', p_table, ' DROP COLUMN ', p_column);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL sp_mig_drop_column_if_exists('demos', 'duracion_max_seg');
CALL sp_mig_drop_column_if_exists('demos', 'tipo_demo');
CALL sp_mig_drop_column_if_exists('demos', 'id_usuario_creador');

CALL sp_mig_drop_column_if_exists('vehiculos', 'soporte_expira_en');
CALL sp_mig_drop_column_if_exists('vehiculos', 'soporte_autorizado');
CALL sp_mig_drop_column_if_exists('vehiculos', 'estado_comercial');
CALL sp_mig_drop_column_if_exists('vehiculos', 'numero_serie');
CALL sp_mig_drop_column_if_exists('vehiculos', 'id_modelo');

DROP PROCEDURE IF EXISTS sp_mig_drop_column_if_exists;
