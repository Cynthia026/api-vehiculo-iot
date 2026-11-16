"""
Pruebas de seguridad de la Práctica 4.3 (92 verificaciones).
SÓLO contra una base MySQL LOCAL de prueba: el script crea datos, desactiva cuentas y rota contraseñas.
Uso (desde la raíz del repositorio):  python3 tests/test_seguridad.py
"""
import os, sys, time, json
API = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, API)
os.environ.update(DB_HOST=os.getenv('TEST_DB_HOST', '127.0.0.1'), DB_PORT=os.getenv('TEST_DB_PORT', '3306'),
                  DB_USER=os.getenv('TEST_DB_USER', 'iot'), DB_PASSWORD=os.getenv('TEST_DB_PASSWORD', 'iotpass'),
                  DB_NAME=os.getenv('TEST_DB_NAME', 'vehiculo_iot'),
                  JWT_SECRET='x' * 48, SEED_ADMIN_PASSWORD='Adm!n-Prueba-2026', SEED_CYNTHIA_PASSWORD='Cyn-Prueba-2026',
                  SEED_CARLOS_PASSWORD='Car-Prueba-2026', SEED_INVITADO_PASSWORD='Inv-Prueba-2026')
if os.environ['DB_HOST'] not in ('127.0.0.1', 'localhost'):
    sys.exit('Por seguridad estas pruebas sólo corren contra una base local (127.0.0.1 / localhost).')
from fastapi.testclient import TestClient
import main
from app.database import db_manager

OK = FALLO = 0
def check(nombre, cond, extra=''):
    global OK, FALLO
    if cond: OK += 1; print(f'  ✅ {nombre}')
    else: FALLO += 1; print(f'  ❌ {nombre}  {extra}')

def q(sql, p=()): return db_manager.execute_query(sql, p)
def cmd_id(veh, nombre): return q("SELECT id_comando FROM comandos WHERE id_vehiculo=%s AND UPPER(nombre)=%s", (veh, nombre.upper()))[0]['id_comando']

with TestClient(main.app) as c:
    H = lambda t: {'Authorization': f'Bearer {t}'}
    def login(email, pwd):
        r = c.post('/api/auth/login', json={'email': email, 'password': pwd})
        return r, (r.json().get('access_token') if r.status_code == 200 else None)

    print('\n[Sin sesión]')
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 1}); check('Sin token NO puede mover la unidad vendida (401)', r.status_code == 401, r.text)
    r = c.get('/api/telemetria/estado/1'); check('Sin token NO lee estado de unidad vendida (401)', r.status_code == 401, r.text)
    r = c.get('/api/telemetria/historial/2'); check('Sin token SÍ lee historial de exhibición (200)', r.status_code == 200, r.text)
    r = c.get('/api/vehiculos/'); check('Sin token sólo ve unidades de exhibición', [v['id_vehiculo'] for v in r.json()] == [2], r.text)
    r = c.put('/api/demos/1', json={'nombre': 'X', 'descripcion': 'x', 'activo': True}); check('Sin token NO edita demos (401)', r.status_code == 401, r.text)
    r = c.get('/api/demos/1/movimientos'); check('Sin token NO ve pasos de demo de unidad vendida (401)', r.status_code == 401, r.text)
    r = c.get('/api/exhibicion/catalogo'); check('Catálogo público disponible (200)', r.status_code == 200, r.text)

    print('\n[Login, contraseñas y límite de intentos]')
    r, tA = login('admin@vehiculoiot.com', 'Admin123*'); check('Contraseña publicada en V001 ya NO funciona (rotada desde .env)', r.status_code == 401, r.text)
    r, tA = login('admin@vehiculoiot.com', 'Adm!n-Prueba-2026'); check('P01 Login Admin con contraseña del .env (200)', r.status_code == 200, r.text)
    for i in range(4): login('carlos@cliente.com', 'mala')
    r, _ = login('carlos@cliente.com', 'mala'); check('5º intento fallido aceptado como 401', r.status_code == 401, r.status_code)
    r, _ = login('carlos@cliente.com', 'Car-Prueba-2026'); check('Tras 5 fallos: bloqueo temporal 429 aunque la contraseña sea correcta', r.status_code == 429, r.text)
    from app.security import limpiar_fallos_login; limpiar_fallos_login('carlos@cliente.com|testclient')
    r, tB = login('carlos@cliente.com', 'Car-Prueba-2026'); check('Carlos entra tras liberar el bloqueo', r.status_code == 200, r.text)
    r, tU = login('cynthia@cliente.com', 'Cyn-Prueba-2026'); check('Login Cynthia (200)', r.status_code == 200, r.text)
    hashes = q("SELECT password_hash FROM usuarios WHERE id_usuario IN (1,2)")
    check('Hashes nuevos con sal aleatoria (no la sal fija iot2026)', all(not h['password_hash'].startswith('sha256$iot2026$') for h in hashes))

    print('\n[RBAC y propiedad (BOLA)]')
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 1}, headers=H(tA)); check('P12 Admin NO opera unidad vendida sin soporte (403)', r.status_code == 403, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 2, 'id_comando': cmd_id(2, 'AVANZAR')}, headers=H(tA)); check('Admin opera unidad de exhibición (200)', r.status_code == 200, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 1}, headers=H(tU)); check('P06 Cynthia opera SU unidad (200)', r.status_code == 200, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 3, 'id_comando': cmd_id(3, 'AVANZAR')}, headers=H(tU)); check('P13 Cynthia NO opera la unidad de Carlos (403)', r.status_code == 403, r.text)
    r = c.get('/api/telemetria/historial/3', headers=H(tU)); check('P04 Cynthia NO ve historial de Carlos (403)', r.status_code == 403, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': cmd_id(3, 'AVANZAR')}, headers=H(tU)); check('Comando de otra unidad rechazado (422)', r.status_code == 422, r.text)
    r = c.get('/api/vehiculos/', headers=H(tU)); check('Cynthia sólo lista su unidad', [v['id_vehiculo'] for v in r.json()] == [1], r.text)
    r = c.patch('/api/mis-vehiculos/1/soporte', json={'autorizado': True, 'minutos': 30}, headers=H(tU)); check('Cynthia autoriza soporte (200)', r.status_code == 200, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 12}, headers=H(tA)); check('Admin opera con soporte autorizado (200)', r.status_code == 200, r.text)

    print('\n[Demos: propiedad y validación]')
    r = c.post('/api/demos/', json={'id_vehiculo': 1, 'nombre': 'Mi rutina', 'descripcion': 'privada'}, headers=H(tU)); check('Cynthia crea demo privada (201)', r.status_code == 201, r.text)
    id_priv = r.json().get('id_demo'); check('La demo queda como PRIVADA', r.json().get('tipo_demo') == 'PRIVADA', r.text)
    r = c.post(f'/api/demos/{id_priv}/movimientos', json={'id_demo': id_priv, 'id_comando': cmd_id(3, 'AVANZAR'), 'orden': 1, 'duracion_ms': 800, 'pausa_ms': 100}, headers=H(tU)); check('Paso con comando de otra unidad rechazado (422)', r.status_code == 422, r.text)
    r = c.post(f'/api/demos/{id_priv}/movimientos', json={'id_demo': id_priv, 'id_comando': 1, 'orden': 1, 'duracion_ms': 50, 'pausa_ms': 100}, headers=H(tU)); check('Duración fuera de rango rechazada (422)', r.status_code == 422, r.text)
    r = c.post(f'/api/demos/{id_priv}/movimientos', json={'id_demo': id_priv, 'id_comando': 1, 'orden': 1, 'duracion_ms': 800, 'pausa_ms': 100}, headers=H(tU)); check('P09 Cynthia agrega paso válido (201)', r.status_code == 201, r.text)
    pasos = c.get(f'/api/demos/{id_priv}/movimientos', headers=H(tU)).json(); id_paso = pasos[0]['id_demo_movimiento']
    r = c.put(f'/api/demos/{id_priv}', json={'nombre': 'Hack', 'descripcion': '', 'activo': True}, headers=H(tB)); check('Carlos NO edita la demo de Cynthia (403)', r.status_code == 403, r.text)
    r = c.delete(f'/api/demos/movimientos/{id_paso}', headers=H(tB)); check('Carlos NO borra pasos de Cynthia (403)', r.status_code == 403, r.text)
    r = c.put(f'/api/demos/{id_priv}', json={'nombre': 'Hack', 'descripcion': '', 'activo': True}, headers=H(tA)); check('Admin NO edita demos privadas de compradores (403)', r.status_code == 403, r.text)
    r = c.put(f'/api/demos/movimientos/{id_paso}', json={'id_comando': 4, 'orden': 1, 'duracion_ms': 900, 'pausa_ms': 0}, headers=H(tU)); check('Cynthia edita su paso (200)', r.status_code == 200, r.text)
    r = c.put('/api/demos/1', json={'nombre': 'DEMO PRINCIPAL', 'descripcion': 'Empresa', 'activo': True}, headers=H(tA)); check('Admin edita demo de EMPRESA (200)', r.status_code == 200, r.text)
    r = c.get('/api/demos/1/movimientos', headers=H(tU)); check('Pasos se leen sin error 500 aunque el SP no traiga id_demo', r.status_code == 200 and r.json()[0]['id_demo'] == 1, r.text)
    r = c.post(f'/api/demos/{id_priv}/ejecutar', params={'id_vehiculo': 3}, headers=H(tB)); check('Carlos NO ejecuta demo de Cynthia en su unidad (403/409)', r.status_code in (403, 409), r.text)

    print('\n[Invitado temporal]')
    r = c.post('/api/auth/invitado', json={'nombre_visitante': 'Visitante 1'}); check('P10 Invitado obtiene sesión temporal (201)', r.status_code == 201, r.text)
    tG = r.json().get('access_token')
    r = c.post('/api/auth/invitado', json={'nombre_visitante': 'Visitante 2'}); check('P14 Segunda sesión sobre la misma unidad rechazada (409)', r.status_code == 409, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 2, 'id_comando': cmd_id(2, 'AVANZAR')}, headers=H(tG)); check('Invitado usa comando permitido (200)', r.status_code == 200, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 2, 'id_comando': cmd_id(2, 'SUBIR_BRAZO')}, headers=H(tG)); check('Invitado NO usa comando restringido (403)', r.status_code == 403, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 1}, headers=H(tG)); check('P12 Invitado NO opera unidad de comprador (403)', r.status_code == 403, r.text)
    r = c.get('/api/admin/dashboard', headers=H(tG)); check('Invitado NO entra a Administración (403)', r.status_code == 403, r.text)
    r = c.post('/api/admin/asignaciones', json={'id_vehiculo': 2, 'id_usuario': 2}, headers=H(tA)); check('No se asigna una unidad mientras un Invitado la usa (409)', r.status_code == 409, r.text)
    db_manager.execute_write("UPDATE sesiones_control SET expira_en = NOW() - INTERVAL 1 SECOND WHERE activa = 1")
    time.sleep(7)
    ses = q("SELECT activa FROM sesiones_control ORDER BY id_sesion DESC LIMIT 1")[0]
    est = q("SELECT c.nombre FROM estado_vehiculo e JOIN comandos c ON c.id_comando=e.id_comando WHERE e.id_vehiculo=2")[0]
    aud = q("SELECT COUNT(*) n FROM bitacora_auditoria WHERE accion='EXPIRACION_INVITADO'")[0]['n']
    check('Al vencer: sesión cerrada, unidad DETENIDA y auditado (sin que el visitante haga nada)', ses['activa'] == 0 and est['nombre'].upper() == 'DETENER' and aud >= 1, f"{ses} {est} {aud}")
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 2, 'id_comando': cmd_id(2, 'AVANZAR')}, headers=H(tG)); check('Token del Invitado vencido rechazado (401)', r.status_code == 401, r.text)

    print('\n[Préstamo del vehículo físico a un Invitado (aprobación del Admin)]')
    r = c.post('/api/auth/invitado/solicitud', json={'nombre_visitante': 'Luis'}); check('P18 Invitado solicita el vehículo físico (201, PENDIENTE)', r.status_code == 201 and r.json().get('estado') == 'PENDIENTE', r.text)
    cod1, id_s1 = r.json().get('codigo'), r.json().get('id_solicitud')
    r = c.post('/api/auth/invitado/solicitud', json={'nombre_visitante': 'Mara'}); cod2, id_s2 = r.json().get('codigo'), r.json().get('id_solicitud')
    check('El código de seguimiento se guarda como hash, no en claro', not q("SELECT 1 FROM solicitudes_invitado WHERE codigo_hash=%s", (cod1,)))
    r = c.get(f'/api/auth/invitado/solicitud/{cod1}'); check('Mientras está PENDIENTE no recibe token', r.json().get('estado') == 'PENDIENTE' and 'access_token' not in r.json(), r.text)
    r = c.get('/api/auth/invitado/solicitud/codigo-inventado'); check('Código inventado: 404', r.status_code == 404, r.text)
    r = c.post(f'/api/admin/solicitudes-invitado/{id_s1}/aprobar'); check('Sin sesión NO se aprueba (401)', r.status_code == 401, r.text)
    r = c.post(f'/api/admin/solicitudes-invitado/{id_s1}/aprobar', headers=H(tU)); check('Un Usuario NO aprueba solicitudes (403)', r.status_code == 403, r.text)
    r = c.get('/api/admin/solicitudes-invitado', headers=H(tA)); check('Admin ve las 2 solicitudes en espera', r.status_code == 200 and len(r.json().get('pendientes', [])) == 2 and r.json().get('prestamo_activo') is None, r.text)
    r = c.post(f'/api/admin/solicitudes-invitado/{id_s1}/aprobar', headers=H(tA)); check('P19 Admin aprueba la solicitud (200)', r.status_code == 200, r.text)
    r = c.post(f'/api/admin/solicitudes-invitado/{id_s1}/aprobar', headers=H(tA)); check('No se aprueba dos veces la misma (409)', r.status_code == 409, r.text)
    r = c.post(f'/api/admin/solicitudes-invitado/{id_s2}/aprobar', headers=H(tA)); check('Sólo un Invitado a la vez: la 2ª aprobación se rechaza (409)', r.status_code == 409, r.text)
    r = c.post('/api/auth/invitado/solicitud', json={'nombre_visitante': 'Otro'}); check('Con el vehículo prestado no se aceptan nuevas solicitudes (409)', r.status_code == 409, r.text)
    r = c.get(f'/api/auth/invitado/solicitud/{cod1}'); tP = r.json().get('access_token')
    check('Al aprobarse, el visitante recibe su token de 3 min', r.json().get('estado') == 'APROBADA' and tP and 170 <= r.json().get('expires_in', 0) <= 180, r.text)
    r = c.get(f'/api/auth/invitado/solicitud/{cod1}'); check('El token se entrega UNA sola vez', 'access_token' not in r.json(), r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': cmd_id(1, 'SUBIR_BRAZO')}, headers=H(tP)); check('Invitado aprobado mueve el vehículo físico con TODOS los comandos (200)', r.status_code == 200, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 3, 'id_comando': cmd_id(3, 'AVANZAR')}, headers=H(tP)); check('El préstamo sólo cubre la unidad física: NO la de Carlos (403)', r.status_code == 403, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 1}, headers=H(tU)); check('Durante el préstamo la dueña queda bloqueada (409)', r.status_code == 409, r.text)
    r = c.get('/api/mis-vehiculos', headers=H(tP)); check('El Invitado sólo ve la unidad prestada', [v['id_vehiculo'] for v in r.json()] == [1], r.text)
    r = c.get('/api/demos/vehiculo/1', headers=H(tP)); check('El Invitado NO ve las demos privadas de la dueña', r.status_code == 200 and all(d.get('tipo_demo') != 'PRIVADA' for d in r.json()) and r.json(), r.text)
    r = c.get(f'/api/demos/{id_priv}/movimientos', headers=H(tP)); check('…ni sus pasos (403)', r.status_code == 403, r.text)
    r = c.post('/api/demos/1/ejecutar', params={'id_vehiculo': 1}, headers=H(tP)); check('Invitado aprobado ejecuta la demo de la empresa (200)', r.status_code == 200, r.text)
    r = c.get('/api/admin/dashboard', headers=H(tP)); check('Invitado aprobado NO entra a Administración (403)', r.status_code == 403, r.text)
    r = c.post('/api/admin/prestamo-fisico/terminar', headers=H(tA)); check('Admin termina el préstamo antes de tiempo (200)', r.status_code == 200, r.text)
    est = q("SELECT c.nombre FROM estado_vehiculo e JOIN comandos c ON c.id_comando=e.id_comando WHERE e.id_vehiculo=1")[0]['nombre']
    check('Al terminar: vehículo físico DETENIDO y demo cancelada', est.upper() == 'DETENER' and 1 not in __import__('app.routers.demos', fromlist=['x']).active_demo_tasks, est)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 1}, headers=H(tP)); check('El token del Invitado deja de servir (401)', r.status_code == 401, r.text)
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 12}, headers=H(tU)); check('La dueña recupera el control (200)', r.status_code == 200, r.text)
    r = c.post(f'/api/admin/solicitudes-invitado/{id_s2}/rechazar', headers=H(tA)); check('Admin rechaza la otra solicitud (200)', r.status_code == 200, r.text)
    r = c.get(f'/api/auth/invitado/solicitud/{cod2}'); check('El visitante ve RECHAZADA y no recibe token', r.json().get('estado') == 'RECHAZADA' and 'access_token' not in r.json(), r.text)
    r = c.post('/api/auth/invitado/solicitud', json={'nombre_visitante': 'Pepe'}); cod3 = r.json().get('codigo')
    r = c.delete(f'/api/auth/invitado/solicitud/{cod3}'); check('El visitante cancela su solicitud (CANCELADA)', r.status_code == 200 and r.json().get('estado') == 'CANCELADA', r.text)
    r = c.post('/api/auth/invitado/solicitud', json={'nombre_visitante': 'Olvidado'}); cod4 = r.json().get('codigo')
    db_manager.execute_write("UPDATE solicitudes_invitado SET creada_en = NOW() - INTERVAL 6 MINUTE WHERE estado='PENDIENTE'")
    r = c.get(f'/api/auth/invitado/solicitud/{cod4}'); check('Solicitud sin respuesta en 5 min: EXPIRADA', r.json().get('estado') == 'EXPIRADA', r.text)
    r = c.post('/api/auth/invitado/solicitud', json={'nombre_visitante': 'Ivan'}); cod5, id_s5 = r.json().get('codigo'), r.json().get('id_solicitud')
    c.post(f'/api/admin/solicitudes-invitado/{id_s5}/aprobar', headers=H(tA))
    tP2 = c.get(f'/api/auth/invitado/solicitud/{cod5}').json().get('access_token')
    c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 1}, headers=H(tP2))
    db_manager.execute_write("UPDATE sesiones_control SET expira_en = NOW() - INTERVAL 1 SECOND WHERE activa = 1 AND tipo_sesion='PRESTAMO_FISICO'")
    time.sleep(7)
    est = q("SELECT c.nombre FROM estado_vehiculo e JOIN comandos c ON c.id_comando=e.id_comando WHERE e.id_vehiculo=1")[0]['nombre']
    sol = q("SELECT estado FROM solicitudes_invitado WHERE id_solicitud=%s", (id_s5,))[0]['estado']
    check('P20 A los 3 min el vigilante DETIENE el vehículo físico y cierra el préstamo', est.upper() == 'DETENER' and sol == 'FINALIZADA', f'{est} {sol}')
    r = c.post('/api/telemetria/movimiento', params={'id_vehiculo': 1, 'id_comando': 1}, headers=H(tP2)); check('Token del préstamo vencido rechazado (401)', r.status_code == 401, r.text)

    print('\n[Administración: CRUD, baja lógica, historial]')
    r = c.put('/api/admin/modelos/2', json={'nombre': 'Rover Explorador IoT', 'descripcion': 'x', 'microcontrolador_default': 'ESP8266', 'tiene_brazo': False, 'tiene_motores_giro': True, 'activo': False}, headers=H(tA)); check('Admin desactiva un modelo (200)', r.status_code == 200, r.text)
    r = c.post('/api/admin/unidades', json={'nombre': 'Unidad 4', 'id_modelo': 2, 'numero_serie': 'SN-ROV-0004'}, headers=H(tA)); check('No se crean unidades de un modelo desactivado (409)', r.status_code == 409, r.text)
    r = c.post('/api/admin/unidades', json={'nombre': 'Unidad 4', 'id_modelo': 1, 'numero_serie': 'SN-EXC-0004'}, headers=H(tA)); check('P02 Admin registra unidad (201)', r.status_code == 201, r.text)
    id4 = r.json().get('id_vehiculo')
    r = c.post('/api/admin/unidades', json={'nombre': 'Copia', 'id_modelo': 1, 'numero_serie': 'sn-exc-0004'}, headers=H(tA)); check('Número de serie duplicado rechazado (409)', r.status_code == 409, r.text)
    r = c.post('/api/admin/clientes', json={'nombre': 'Ana Prueba', 'email': 'ana@cliente.com', 'password': 'Ana-Prueba-2026'}, headers=H(tA)); check('P03 Admin registra cliente (201)', r.status_code == 201, r.text)
    id_ana = r.json().get('id_usuario')
    r = c.post('/api/admin/asignaciones', json={'id_vehiculo': id4, 'id_usuario': id_ana}, headers=H(tA)); check('P04 Admin asigna unidad (201)', r.status_code == 201, r.text)
    r = c.delete(f'/api/vehiculos/{id4}', headers=H(tA)); check('No se da de baja una unidad con comprador (409)', r.status_code == 409, r.text)
    r = c.delete(f'/api/admin/asignaciones/{id4}', headers=H(tA)); check('Admin revoca asignación (200)', r.status_code == 200, r.text)
    r = c.delete(f'/api/vehiculos/{id4}', headers=H(tA)); check('Baja de unidad (204)', r.status_code == 204, r.text)
    fila = q("SELECT activo, estado_comercial FROM vehiculos WHERE id_vehiculo=%s", (id4,))
    check('Baja LÓGICA: la fila sigue existiendo (activo=0, INACTIVO)', fila and fila[0]['activo'] == 0 and fila[0]['estado_comercial'] == 'INACTIVO', fila)
    hist = q("SELECT COUNT(*) n FROM asignaciones_vehiculo WHERE id_vehiculo=%s", (id4,))[0]['n']
    check('La asignación revocada se conserva como historial', hist == 1, hist)
    r = c.put(f'/api/admin/clientes/3', json={'nombre': 'Carlos Mendoza', 'email': 'carlos@cliente.com', 'activo': False}, headers=H(tA)); check('Admin desactiva a Carlos (200)', r.status_code == 200, r.text)
    r = c.get('/api/mis-vehiculos', headers=H(tB)); check('El token de Carlos deja de funcionar al desactivarlo (401)', r.status_code == 401, r.text)
    c.put(f'/api/admin/clientes/3', json={'nombre': 'Carlos Mendoza', 'email': 'carlos@cliente.com', 'activo': True}, headers=H(tA))

    print('\n[Logout e invalidación]')
    r = c.post('/api/auth/logout', headers=H(tU)); check('P? Cynthia cierra sesión (200)', r.status_code == 200, r.text)
    r = c.get('/api/mis-vehiculos', headers=H(tU)); check('Token usado tras logout rechazado (401)', r.status_code == 401, r.text)

    print('\n[Persistencia tras reinicio]')
    c.delete('/api/admin/asignaciones/1', headers=H(tA))
    db_manager.ensure_schema_4_3()
    est1 = q("SELECT estado_comercial FROM vehiculos WHERE id_vehiculo=1")[0]['estado_comercial']
    act = q("SELECT COUNT(*) n FROM asignaciones_vehiculo WHERE id_vehiculo=1 AND activo=1")[0]['n']
    check('Reiniciar la API ya NO reasigna la Unidad 1 a Cynthia', est1 == 'DISPONIBLE' and act == 0, f'{est1} {act}')

    print('\n[Vehículo físico (WebSocket)]')
    with c.websocket_connect('/api/demos/ws/1') as ws:
        msg = ws.receive_json(); check('El ESP32 sigue conectándose al WSS y recibe el estado inicial', msg.get('tipo_evento') == 'estado_inicial', msg)

    aud = q("SELECT accion, COUNT(*) n FROM bitacora_auditoria GROUP BY accion ORDER BY accion")
    print('\nAuditoría registrada:', ', '.join(f"{a['accion']}({a['n']})" for a in aud))

print(f'\nRESULTADO: {OK} correctas, {FALLO} con fallo')
