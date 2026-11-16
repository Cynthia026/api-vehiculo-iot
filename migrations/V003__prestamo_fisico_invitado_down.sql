-- =====================================================================
-- V003 · Reversión (sólo entorno de prueba). Respalda antes de ejecutar.
-- =====================================================================
-- Cierra cualquier préstamo físico en curso antes de quitar la tabla
UPDATE sesiones_control SET activa = 0 WHERE tipo_sesion = 'PRESTAMO_FISICO' AND activa = 1;
DROP TABLE IF EXISTS solicitudes_invitado;
