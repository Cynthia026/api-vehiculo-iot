-- ============================================================================
-- ARCHIVO: 00_precheck_and_counts.sql
-- PROPÓSITO: Diagnóstico y conteo previo antes de ejecutar la migración V001
-- BASE DE DATOS: vehiculo_iot (Amazon RDS MySQL)
-- ============================================================================

USE vehiculo_iot;

-- 1. Verificar versión de MySQL y base de datos activa
SELECT DATABASE() AS base_datos_activa, VERSION() AS version_mysql, NOW() AS fecha_verificacion;

-- 2. Conteo de registros actuales en las 6 tablas de 4.1 y 4.2 (DEBEN CONSERVARSE)
SELECT 'vehiculos' AS tabla, COUNT(*) AS total_registros FROM vehiculos
UNION ALL
SELECT 'comandos', COUNT(*) FROM comandos
UNION ALL
SELECT 'estado_vehiculo', COUNT(*) FROM estado_vehiculo
UNION ALL
SELECT 'historial_comandos', COUNT(*) FROM historial_comandos
UNION ALL
SELECT 'demos', COUNT(*) FROM demos
UNION ALL
SELECT 'demo_movimientos', COUNT(*) FROM demo_movimientos;

-- 3. Verificar que la Unidad 1 y sus comandos existan
SELECT id_vehiculo, nombre, modelo, microcontrolador, activo FROM vehiculos ORDER BY id_vehiculo;
SELECT id_comando, id_vehiculo, nombre, codigo, activo FROM comandos WHERE id_vehiculo = 1 ORDER BY id_comando;

-- 4. Inventario de los Stored Procedures actuales (21 SPs esperados)
SELECT ROUTINE_NAME, ROUTINE_TYPE, CREATED, LAST_ALTERED
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE()
ORDER BY ROUTINE_NAME;
