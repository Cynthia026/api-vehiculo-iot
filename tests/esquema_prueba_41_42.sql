-- Esquema base 4.1/4.2 reconstruido SOLO para pruebas locales (a partir del uso que hace la API).
CREATE TABLE vehiculos (
  id_vehiculo INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(80) NOT NULL, modelo VARCHAR(80) NOT NULL, descripcion VARCHAR(255) NULL,
  microcontrolador VARCHAR(50) NOT NULL DEFAULT 'ESP8266', activo TINYINT(1) NOT NULL DEFAULT 1,
  fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE comandos (
  id_comando INT AUTO_INCREMENT PRIMARY KEY, id_vehiculo INT NOT NULL, nombre VARCHAR(60) NOT NULL,
  codigo INT NOT NULL, descripcion VARCHAR(255) NULL, activo TINYINT(1) NOT NULL DEFAULT 1,
  FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE estado_vehiculo (
  id_estado INT AUTO_INCREMENT PRIMARY KEY, id_vehiculo INT NOT NULL UNIQUE, id_comando INT NOT NULL,
  conectado TINYINT(1) NOT NULL DEFAULT 1, fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo), FOREIGN KEY (id_comando) REFERENCES comandos(id_comando)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE historial_movimientos (
  id_historial INT AUTO_INCREMENT PRIMARY KEY, id_vehiculo INT NOT NULL, id_comando INT NOT NULL,
  origen VARCHAR(30) NOT NULL, fecha_hora TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo), FOREIGN KEY (id_comando) REFERENCES comandos(id_comando)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE demos (
  id_demo INT AUTO_INCREMENT PRIMARY KEY, id_vehiculo INT NOT NULL, nombre VARCHAR(80) NOT NULL,
  descripcion VARCHAR(255) NULL, activo TINYINT(1) NOT NULL DEFAULT 1,
  FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE demo_movimientos (
  id_demo_movimiento INT AUTO_INCREMENT PRIMARY KEY, id_demo INT NOT NULL, id_comando INT NOT NULL,
  orden INT NOT NULL, duracion_ms INT NOT NULL, pausa_ms INT NOT NULL DEFAULT 0,
  FOREIGN KEY (id_demo) REFERENCES demos(id_demo) ON DELETE CASCADE, FOREIGN KEY (id_comando) REFERENCES comandos(id_comando)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELIMITER //
CREATE PROCEDURE sp_obtener_vehiculos() BEGIN SELECT * FROM vehiculos ORDER BY id_vehiculo; END//
CREATE PROCEDURE sp_obtener_vehiculo(IN p INT) BEGIN SELECT * FROM vehiculos WHERE id_vehiculo = p; END//
CREATE PROCEDURE sp_crear_vehiculo(IN n VARCHAR(80), IN m VARCHAR(80), IN d VARCHAR(255), IN mc VARCHAR(50)) BEGIN INSERT INTO vehiculos (nombre, modelo, descripcion, microcontrolador) VALUES (n, m, d, mc); SELECT * FROM vehiculos WHERE id_vehiculo = LAST_INSERT_ID(); END//
CREATE PROCEDURE sp_actualizar_vehiculo(IN p INT, IN n VARCHAR(80), IN m VARCHAR(80), IN d VARCHAR(255), IN mc VARCHAR(50), IN a TINYINT) BEGIN UPDATE vehiculos SET nombre=n, modelo=m, descripcion=d, microcontrolador=mc, activo=a WHERE id_vehiculo=p; SELECT * FROM vehiculos WHERE id_vehiculo=p; END//
CREATE PROCEDURE sp_eliminar_vehiculo(IN p INT) BEGIN DELETE FROM vehiculos WHERE id_vehiculo = p; END//
CREATE PROCEDURE sp_obtener_comandos_vehiculo(IN p INT) BEGIN SELECT * FROM comandos WHERE id_vehiculo = p ORDER BY id_comando; END//
CREATE PROCEDURE sp_crear_comando(IN v INT, IN n VARCHAR(60), IN c INT, IN d VARCHAR(255)) BEGIN INSERT INTO comandos (id_vehiculo, nombre, codigo, descripcion) VALUES (v, n, c, d); END//
CREATE PROCEDURE sp_actualizar_comando(IN p INT, IN n VARCHAR(60), IN c INT, IN d VARCHAR(255), IN a TINYINT) BEGIN UPDATE comandos SET nombre=n, codigo=c, descripcion=d, activo=a WHERE id_comando=p; END//
CREATE PROCEDURE sp_eliminar_comando(IN p INT) BEGIN DELETE FROM comandos WHERE id_comando = p; END//
CREATE PROCEDURE sp_actualizar_estado(IN v INT, IN c INT, IN con TINYINT) BEGIN INSERT INTO estado_vehiculo (id_vehiculo, id_comando, conectado) VALUES (v, c, con) ON DUPLICATE KEY UPDATE id_comando=c, conectado=con, fecha_actualizacion=NOW(); END//
CREATE PROCEDURE sp_obtener_estado(IN v INT) BEGIN SELECT e.id_vehiculo, ve.nombre AS vehiculo, e.id_comando, c.nombre AS comando, c.codigo, e.conectado, e.fecha_actualizacion FROM estado_vehiculo e JOIN vehiculos ve ON ve.id_vehiculo=e.id_vehiculo JOIN comandos c ON c.id_comando=e.id_comando WHERE e.id_vehiculo = v; END//
CREATE PROCEDURE sp_registrar_historial(IN v INT, IN c INT, IN o VARCHAR(30)) BEGIN INSERT INTO historial_movimientos (id_vehiculo, id_comando, origen) VALUES (v, c, o); END//
CREATE PROCEDURE sp_obtener_historial(IN v INT) BEGIN SELECT h.id_historial, h.id_vehiculo, c.nombre AS comando, c.codigo, h.fecha_hora, h.origen FROM historial_movimientos h JOIN comandos c ON c.id_comando=h.id_comando WHERE h.id_vehiculo = v ORDER BY h.id_historial DESC; END//
CREATE PROCEDURE sp_obtener_demos(IN v INT) BEGIN SELECT id_demo, id_vehiculo, nombre, descripcion, activo FROM demos WHERE id_vehiculo = v ORDER BY id_demo; END//
CREATE PROCEDURE sp_crear_demo(IN v INT, IN n VARCHAR(80), IN d VARCHAR(255)) BEGIN INSERT INTO demos (id_vehiculo, nombre, descripcion) VALUES (v, n, d); END//
CREATE PROCEDURE sp_actualizar_demo(IN p INT, IN n VARCHAR(80), IN d VARCHAR(255), IN a TINYINT) BEGIN UPDATE demos SET nombre=n, descripcion=d, activo=a WHERE id_demo=p; END//
CREATE PROCEDURE sp_eliminar_demo(IN p INT) BEGIN DELETE FROM demos WHERE id_demo = p; END//
CREATE PROCEDURE sp_agregar_movimiento_demo(IN dm INT, IN c INT, IN o INT, IN du INT, IN pa INT) BEGIN INSERT INTO demo_movimientos (id_demo, id_comando, orden, duracion_ms, pausa_ms) VALUES (dm, c, o, du, pa); END//
-- Igual que el caso real que daba 500: NO devuelve id_demo
CREATE PROCEDURE sp_obtener_movimientos_demo(IN dm INT) BEGIN SELECT m.id_demo_movimiento, m.id_comando, c.nombre AS comando, m.orden, m.duracion_ms, m.pausa_ms FROM demo_movimientos m JOIN comandos c ON c.id_comando=m.id_comando WHERE m.id_demo = dm ORDER BY m.orden; END//
CREATE PROCEDURE sp_actualizar_movimiento_demo(IN p INT, IN c INT, IN o INT, IN du INT, IN pa INT) BEGIN UPDATE demo_movimientos SET id_comando=c, orden=o, duracion_ms=du, pausa_ms=pa WHERE id_demo_movimiento=p; END//
CREATE PROCEDURE sp_eliminar_movimiento_demo(IN p INT) BEGIN DELETE FROM demo_movimientos WHERE id_demo_movimiento = p; END//
DELIMITER ;

INSERT INTO vehiculos (nombre, modelo, microcontrolador) VALUES ('Excavadora IoT', 'Modelo X', 'ESP32');
INSERT INTO comandos (id_vehiculo, nombre, codigo) VALUES
 (1,'AVANZAR',1),(1,'RETROCEDER',2),(1,'GIRAR_IZQUIERDA',3),(1,'GIRAR_DERECHA',4),(1,'SUBIR_BRAZO',5),(1,'BAJAR_BRAZO',6),
 (1,'MOTOR_IZQUIERDA',7),(1,'MOTOR_DERECHA',8),(1,'VELOCIDAD',9),(1,'SONIDO',10),(1,'LUZ',11),(1,'Detener',12);
INSERT INTO estado_vehiculo (id_vehiculo, id_comando, conectado) VALUES (1, 12, 1);
INSERT INTO demos (id_vehiculo, nombre, descripcion) VALUES (1, 'DEMO PRINCIPAL', 'Todos los movimientos');
INSERT INTO demo_movimientos (id_demo, id_comando, orden, duracion_ms, pausa_ms) VALUES (1,1,1,300,100),(1,4,2,300,0);
