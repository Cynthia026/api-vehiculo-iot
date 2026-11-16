-- =====================================================================
-- V002 · Reversión (sólo entorno de prueba). Respalda antes de ejecutar.
-- =====================================================================
DROP TABLE IF EXISTS tokens_revocados;

-- Las unidades dadas de baja vuelven a estado DISPONIBLE pero siguen inactivas
-- (se revisan manualmente antes de reactivarlas).
UPDATE vehiculos SET estado_comercial = 'DISPONIBLE' WHERE estado_comercial = 'INACTIVO';
