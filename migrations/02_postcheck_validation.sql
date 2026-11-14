-- ============================================================================
-- ARCHIVO: 02_postcheck_validation.sql
-- PROPÓSITO: Verificación posterior a la migración V001 (conteos, relaciones
--            y compatibilidad con los Stored Procedures originales).
-- ============================================================================

USE vehiculo_iot;

-- 1. Comprobar conteos de las 6 tablas originales + las 6 tablas nuevas
SELECT 'vehiculos' AS tabla, COUNT(*) AS total FROM vehiculos
UNION ALL SELECT 'comandos', COUNT(*) FROM comandos
UNION ALL SELECT 'estado_vehiculo', COUNT(*) FROM estado_vehiculo
UNION ALL SELECT 'historial_comandos', COUNT(*) FROM historial_comandos
UNION ALL SELECT 'demos', COUNT(*) FROM demos
UNION ALL SELECT 'demo_movimientos', COUNT(*) FROM demo_movimientos
UNION ALL SELECT 'roles (NUEVA)', COUNT(*) FROM roles
UNION ALL SELECT 'usuarios (NUEVA)', COUNT(*) FROM usuarios
UNION ALL SELECT 'modelos_catalogo (NUEVA)', COUNT(*) FROM modelos_catalogo
UNION ALL SELECT 'asignaciones_vehiculo (NUEVA)', COUNT(*) FROM asignaciones_vehiculo
UNION ALL SELECT 'sesiones_control (NUEVA)', COUNT(*) FROM sesiones_control
UNION ALL SELECT 'bitacora_auditoria (NUEVA)', COUNT(*) FROM bitacora_auditoria;

-- 2. Verificar unidades físicas y su estado comercial / asignación
SELECT v.id_vehiculo, v.nombre, v.modelo, v.numero_serie, v.estado_comercial,
       v.soporte_autorizado, u.nombre AS propietario, u.email AS email_propietario
FROM vehiculos v
LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo = v.id_vehiculo AND a.activo = 1
LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
ORDER BY v.id_vehiculo;

-- 3. Probar que los Stored Procedures existentes de 4.1 / 4.2 siguen funcionando
CALL sp_obtener_vehiculos();
CALL sp_obtener_comandos_vehiculo(1);
CALL sp_obtener_estado(1);
CALL sp_obtener_historial(1);
CALL sp_obtener_demos(1);
