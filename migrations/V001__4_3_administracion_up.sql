-- ============================================================================
-- ARCHIVO: V001__4_3_administracion_up.sql
-- PROPÓSITO: Migración incremental NO DESTRUCTIVA para Práctica 4.3 Administración
-- COMPATIBILIDAD: MySQL 8.0 / Amazon RDS (vehiculo_iot)
-- NOTA TÉCNICA: En MySQL las sentencias DDL (CREATE/ALTER/DROP) ejecutan un
-- COMMIT implícito. Asegúrate de realizar un respaldo previo (mysqldump o
-- Snapshot en RDS) antes de ejecutar este script.
-- ============================================================================

USE vehiculo_iot;

-- ============================================================================
-- 1. CREACIÓN DE TABLAS NUEVAS (RBAC, MODELOS COMERCIALES, ASIGNACIONES,
--    RESERVAS DE SESIÓN Y BITÁCORA DE AUDITORÍA)
-- ============================================================================

CREATE TABLE IF NOT EXISTS roles (
    id_rol INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE COMMENT 'ADMIN | USUARIO | INVITADO',
    nombre VARCHAR(60) NOT NULL,
    descripcion VARCHAR(255) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    id_rol INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL COMMENT 'Formato pbkdf2_sha256$salt$hash',
    activo TINYINT(1) NOT NULL DEFAULT 1,
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_usuarios_rol FOREIGN KEY (id_rol) REFERENCES roles(id_rol)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_usuarios_rol (id_rol),
    INDEX idx_usuarios_activo (activo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS modelos_catalogo (
    id_modelo INT AUTO_INCREMENT PRIMARY KEY,
    codigo_modelo VARCHAR(40) NOT NULL UNIQUE COMMENT 'Código comercial único, ej. EXC-IOT-V1',
    nombre VARCHAR(80) NOT NULL,
    descripcion VARCHAR(255) NULL,
    microcontrolador_default VARCHAR(50) NOT NULL DEFAULT 'ESP8266',
    tiene_brazo TINYINT(1) NOT NULL DEFAULT 1,
    tiene_motores_giro TINYINT(1) NOT NULL DEFAULT 1,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
        ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_asig_vehiculo_activo (id_vehiculo, activo),
    INDEX idx_asig_usuario_activo (id_usuario, activo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sesiones_control (
    id_sesion INT AUTO_INCREMENT PRIMARY KEY,
    id_vehiculo INT NOT NULL,
    id_usuario INT NULL COMMENT 'NULL cuando es invitado temporal anónimo o ID del usuario',
    token_jti VARCHAR(80) NOT NULL UNIQUE,
    nombre_operador VARCHAR(100) NULL,
    tipo_sesion VARCHAR(30) NOT NULL DEFAULT 'INVITADO' COMMENT 'PROPIETARIO | INVITADO | SOPORTE_ADMIN',
    inicio_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_en DATETIME NOT NULL,
    activa TINYINT(1) NOT NULL DEFAULT 1,
    CONSTRAINT fk_sesion_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_sesion_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_sesion_vehiculo_activa (id_vehiculo, activa, expira_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bitacora_auditoria (
    id_auditoria BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NULL,
    rol VARCHAR(30) NOT NULL,
    accion VARCHAR(60) NOT NULL COMMENT 'LOGIN | ALTA_UNIDAD | ASIGNACION | REVOCACION | DEMO | SOPORTE | RESERVA_INVITADO',
    entidad VARCHAR(50) NOT NULL,
    id_recurso INT NULL,
    detalle VARCHAR(500) NULL,
    ip_origen VARCHAR(60) NULL,
    fecha_hora TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_audit_fecha (fecha_hora DESC),
    INDEX idx_audit_accion (accion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 2. AMPLIACIÓN ADITIVA E IDEMPOTENTE DE TABLAS EXISTENTES (vehiculos y demos)
--    Conserva intactos todos los datos y los 21 Stored Procedures actuales.
-- ============================================================================

DROP PROCEDURE IF EXISTS sp_mig_add_column_if_not_exists;
DELIMITER $$
CREATE PROCEDURE sp_mig_add_column_if_not_exists(
    IN p_table VARCHAR(64),
    IN p_column VARCHAR(64),
    IN p_definition VARCHAR(255)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table
          AND COLUMN_NAME = p_column
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE ', p_table, ' ADD COLUMN ', p_column, ' ', p_definition);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- Nuevas columnas en vehiculos (distingue Modelo Comercial de Unidad Física)
CALL sp_mig_add_column_if_not_exists('vehiculos', 'id_modelo', 'INT NULL');
CALL sp_mig_add_column_if_not_exists('vehiculos', 'numero_serie', 'VARCHAR(60) NULL UNIQUE');
CALL sp_mig_add_column_if_not_exists('vehiculos', 'estado_comercial', "VARCHAR(30) NOT NULL DEFAULT 'DISPONIBLE'");
CALL sp_mig_add_column_if_not_exists('vehiculos', 'soporte_autorizado', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL sp_mig_add_column_if_not_exists('vehiculos', 'soporte_expira_en', 'DATETIME NULL');

-- Nuevas columnas en demos (distingue demos de EMPRESA, PRIVADA y EXHIBICION)
CALL sp_mig_add_column_if_not_exists('demos', 'id_usuario_creador', 'INT NULL');
CALL sp_mig_add_column_if_not_exists('demos', 'tipo_demo', "VARCHAR(20) NOT NULL DEFAULT 'EMPRESA'");
CALL sp_mig_add_column_if_not_exists('demos', 'duracion_max_seg', 'INT NOT NULL DEFAULT 60');

DROP PROCEDURE IF EXISTS sp_mig_add_column_if_not_exists;

-- ============================================================================
-- 3. POBLADO CONTROLADO DE DATOS SEMILLA (ROLES, MODELOS, USUARIOS Y UNIDADES)
-- ============================================================================

-- 3.1 Roles del sistema
INSERT INTO roles (id_rol, codigo, nombre, descripcion) VALUES
    (1, 'ADMIN', 'Administrador', 'Empresa propietaria: gestiona catálogo, inventario, clientes, asignaciones y demos de fábrica'),
    (2, 'USUARIO', 'Usuario Comprador', 'Cliente propietario: opera y monitorea exclusivamente sus unidades asignadas y crea demos privadas'),
    (3, 'INVITADO', 'Invitado', 'Cliente potencial: explora catálogo público y realiza prueba temporal controlada en unidad de exhibición')
ON DUPLICATE KEY UPDATE
    nombre = VALUES(nombre),
    descripcion = VALUES(descripcion);

-- 3.2 Modelos comerciales de catálogo
INSERT INTO modelos_catalogo (id_modelo, codigo_modelo, nombre, descripcion, microcontrolador_default, tiene_brazo, tiene_motores_giro, activo) VALUES
    (1, 'EXC-IOT-V1', 'Excavadora IoT', 'Vehículo oruga con brazo hidráulico articulado, giro de cabina y accesorios luminosos/sonoros.', 'ESP8266', 1, 1, 1),
    (2, 'ROV-IOT-V1', 'Rover Explorador IoT', 'Vehículo compacto de exploración 4WD con tracción diferencial, faros LED y telemetría.', 'ESP8266', 0, 1, 1)
ON DUPLICATE KEY UPDATE
    nombre = VALUES(nombre),
    descripcion = VALUES(descripcion);

-- 3.3 Usuarios iniciales (Contraseñas hasheadas con SHA2 nativo de MySQL + salt 'iot2026')
-- Claves de acceso:
--   admin@vehiculoiot.com    -> Admin123*
--   cynthia@cliente.com      -> Cliente123*
--   carlos@cliente.com       -> Cliente123*
--   invitado@vehiculoiot.com -> Invitado123*
INSERT INTO usuarios (id_usuario, id_rol, nombre, email, password_hash, activo) VALUES
    (1, 1, 'Administrador General', 'admin@vehiculoiot.com', CONCAT('sha256$iot2026$', LOWER(SHA2('iot2026:Admin123*', 256))), 1),
    (2, 2, 'Cynthia Martínez García', 'cynthia@cliente.com', CONCAT('sha256$iot2026$', LOWER(SHA2('iot2026:Cliente123*', 256))), 1),
    (3, 2, 'Carlos Mendoza (Comprador B)', 'carlos@cliente.com', CONCAT('sha256$iot2026$', LOWER(SHA2('iot2026:Cliente123*', 256))), 1),
    (4, 3, 'Invitado Demo', 'invitado@vehiculoiot.com', CONCAT('sha256$iot2026$', LOWER(SHA2('iot2026:Invitado123*', 256))), 1)
ON DUPLICATE KEY UPDATE
    nombre = VALUES(nombre),
    id_rol = VALUES(id_rol),
    password_hash = VALUES(password_hash);

-- 3.4 Actualizar metadatos comerciales de la Unidad 1 existente (sin cambiar su ID ni su historial)
UPDATE vehiculos
SET id_modelo = 1,
    numero_serie = COALESCE(numero_serie, 'SN-EXC-0001'),
    estado_comercial = 'VENDIDO'
WHERE id_vehiculo = 1;

-- 3.5 Crear Unidad 2 de EXHIBICIÓN (para sesiones temporales de Invitados) si no existe
INSERT INTO vehiculos (id_vehiculo, nombre, modelo, descripcion, microcontrolador, activo, id_modelo, numero_serie, estado_comercial, soporte_autorizado)
SELECT 2, 'Unidad 2 - Showroom', 'Excavadora IoT', 'Unidad física de exhibición para demostraciones temporales de clientes potenciales.', 'ESP8266', 1, 1, 'SN-EXC-DEMO-02', 'EXHIBICION', 1
WHERE NOT EXISTS (SELECT 1 FROM vehiculos WHERE id_vehiculo = 2);

-- 3.6 Crear Unidad 3 asignada al Usuario B (para pruebas de bloqueo cruzado BOLA/IDOR) si no existe
INSERT INTO vehiculos (id_vehiculo, nombre, modelo, descripcion, microcontrolador, activo, id_modelo, numero_serie, estado_comercial, soporte_autorizado)
SELECT 3, 'Unidad 3 - Rover Norte', 'Rover Explorador IoT', 'Unidad adquirida por cliente externo para pruebas de aislamiento entre cuentas.', 'ESP8266', 1, 2, 'SN-ROV-0003', 'VENDIDO', 0
WHERE NOT EXISTS (SELECT 1 FROM vehiculos WHERE id_vehiculo = 3);

-- 3.7 Clonar catálogo de comandos base hacia Unidad 2 y Unidad 3 si aún no tienen comandos registrados
INSERT INTO comandos (id_vehiculo, nombre, codigo, descripcion, activo)
SELECT 2, c.nombre, c.codigo, c.descripcion, c.activo
FROM comandos c
WHERE c.id_vehiculo = 1
  AND NOT EXISTS (SELECT 1 FROM comandos c2 WHERE c2.id_vehiculo = 2);

INSERT INTO comandos (id_vehiculo, nombre, codigo, descripcion, activo)
SELECT 3, c.nombre, c.codigo, c.descripcion,
       CASE WHEN c.nombre IN ('SUBIR_BRAZO', 'BAJAR_BRAZO') THEN 0 ELSE c.activo END
FROM comandos c
WHERE c.id_vehiculo = 1
  AND NOT EXISTS (SELECT 1 FROM comandos c3 WHERE c3.id_vehiculo = 3);

-- 3.8 Inicializar estado_vehiculo para Unidades 2 y 3 si aún no tienen fila de estado
INSERT INTO estado_vehiculo (id_vehiculo, id_comando, conectado)
SELECT 2, (SELECT id_comando FROM comandos WHERE id_vehiculo = 2 AND nombre = 'Detener' LIMIT 1), 1
WHERE NOT EXISTS (SELECT 1 FROM estado_vehiculo WHERE id_vehiculo = 2)
  AND EXISTS (SELECT 1 FROM comandos WHERE id_vehiculo = 2 AND nombre = 'Detener');

INSERT INTO estado_vehiculo (id_vehiculo, id_comando, conectado)
SELECT 3, (SELECT id_comando FROM comandos WHERE id_vehiculo = 3 AND nombre = 'Detener' LIMIT 1), 1
WHERE NOT EXISTS (SELECT 1 FROM estado_vehiculo WHERE id_vehiculo = 3)
  AND EXISTS (SELECT 1 FROM comandos WHERE id_vehiculo = 3 AND nombre = 'Detener');

-- 3.9 Crear una DEMO de exhibición para la Unidad 2 si no existe
INSERT INTO demos (id_vehiculo, nombre, descripcion, activo, id_usuario_creador, tipo_demo, duracion_max_seg)
SELECT 2, 'DEMO EXHIBICIÓN SHOWROOM', 'Rutina de demostración segura para visitantes e invitados.', 1, 1, 'EXHIBICION', 30
WHERE NOT EXISTS (SELECT 1 FROM demos WHERE id_vehiculo = 2);

-- Insertar pasos para la demo de exhibición de la Unidad 2 si está vacía
INSERT INTO demo_movimientos (id_demo, id_comando, orden, duracion_ms, pausa_ms)
SELECT d.id_demo,
       (SELECT id_comando FROM comandos WHERE id_vehiculo = 2 AND nombre = 'AVANZAR' LIMIT 1),
       1, 1500, 400
FROM demos d
WHERE d.id_vehiculo = 2
  AND NOT EXISTS (SELECT 1 FROM demo_movimientos dm WHERE dm.id_demo = d.id_demo)
  AND EXISTS (SELECT 1 FROM comandos WHERE id_vehiculo = 2 AND nombre = 'AVANZAR');

INSERT INTO demo_movimientos (id_demo, id_comando, orden, duracion_ms, pausa_ms)
SELECT d.id_demo,
       (SELECT id_comando FROM comandos WHERE id_vehiculo = 2 AND nombre = 'GIRAR_DERECHA' LIMIT 1),
       2, 1200, 400
FROM demos d
WHERE d.id_vehiculo = 2
  AND (SELECT COUNT(*) FROM demo_movimientos dm WHERE dm.id_demo = d.id_demo) = 1
  AND EXISTS (SELECT 1 FROM comandos WHERE id_vehiculo = 2 AND nombre = 'GIRAR_DERECHA');

INSERT INTO demo_movimientos (id_demo, id_comando, orden, duracion_ms, pausa_ms)
SELECT d.id_demo,
       (SELECT id_comando FROM comandos WHERE id_vehiculo = 2 AND nombre = 'Detener' LIMIT 1),
       3, 1000, 300
FROM demos d
WHERE d.id_vehiculo = 2
  AND (SELECT COUNT(*) FROM demo_movimientos dm WHERE dm.id_demo = d.id_demo) = 2
  AND EXISTS (SELECT 1 FROM comandos WHERE id_vehiculo = 2 AND nombre = 'Detener');

-- 3.10 Registrar asignaciones de propiedad (Unidad 1 -> Cynthia, Unidad 3 -> Carlos)
INSERT INTO asignaciones_vehiculo (id_vehiculo, id_usuario, notas, activo)
SELECT 1, 2, 'Asignación titular de Unidad 1 (Excavadora IoT) a Cynthia Martínez García', 1
WHERE NOT EXISTS (SELECT 1 FROM asignaciones_vehiculo WHERE id_vehiculo = 1 AND activo = 1);

INSERT INTO asignaciones_vehiculo (id_vehiculo, id_usuario, notas, activo)
SELECT 3, 3, 'Asignación titular de Unidad 3 (Rover Norte) a Carlos Mendoza', 1
WHERE NOT EXISTS (SELECT 1 FROM asignaciones_vehiculo WHERE id_vehiculo = 3 AND activo = 1);

-- 3.11 Registrar evento inicial en bitácora de auditoría
INSERT INTO bitacora_auditoria (id_usuario, rol, accion, entidad, id_recurso, detalle, ip_origen)
SELECT 1, 'ADMIN', 'MIGRACION_4_3', 'SISTEMA', 1, 'Migración V001 aplicada: RBAC, modelos comerciales, asignaciones y unidad de exhibición configurados.', '127.0.0.1'
WHERE NOT EXISTS (SELECT 1 FROM bitacora_auditoria WHERE accion = 'MIGRACION_4_3');
