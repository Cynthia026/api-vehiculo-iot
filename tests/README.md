# Pruebas automáticas de seguridad (Práctica 4.3)

`test_seguridad.py` levanta la API con `TestClient` y comprueba **92 reglas** contra una base MySQL/MariaDB **local**:
sin sesión, login y límite de intentos, BOLA, privacidad con soporte, propiedad de demos, Invitado (comandos,
exclusividad y DETENER automático al vencer), préstamo del vehículo físico con aprobación del Admin, CRUD con baja lógica, logout/invalidación, persistencia tras reinicio y WebSocket.

> ⚠️ Nunca contra RDS de producción: crea datos, desactiva cuentas y rota contraseñas. El script se niega a correr si `DB_HOST` no es local.

```bash
# 1) Base local de prueba
mysql -uroot -e "CREATE DATABASE vehiculo_iot CHARACTER SET utf8mb4; CREATE USER 'iot'@'127.0.0.1' IDENTIFIED BY 'iotpass'; GRANT ALL ON vehiculo_iot.* TO 'iot'@'127.0.0.1';"
mysql -uroot --default-character-set=utf8mb4 vehiculo_iot < tests/esquema_prueba_41_42.sql
mysql -uroot --default-character-set=utf8mb4 vehiculo_iot < migrations/V001__4_3_administracion_up.sql
# 2) Pruebas
pip install -r requirements.txt httpx
python3 tests/test_seguridad.py
```

`esquema_prueba_41_42.sql` es una **reconstrucción** de las tablas y procedimientos de 4.1/4.2 a partir de cómo los usa la API,
sólo para pruebas; la fuente de verdad es tu esquema en RDS.
