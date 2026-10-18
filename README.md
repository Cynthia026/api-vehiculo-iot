# API Vehículo IoT - Documentación Técnica

Este repositorio contiene el backend (API REST y WebSockets) desarrollado con **FastAPI** y desplegado en **AWS EC2** para el control y telemetría de una Excavadora IoT.

## 1. Mapeo de Endpoints y Procedimientos Almacenados (RDS)
La API delega toda la lógica de negocio y persistencia a una base de datos MySQL en Amazon RDS. A continuación, se detalla la relación entre los endpoints de la API y los Procedimientos Almacenados (SPs) ejecutados:

### Módulo de Secuencias DEMO y Control (`/api/demos`)

| Endpoint | Método | Procedimiento Almacenado (SP) | Descripción |
| :--- | :--- | :--- | :--- |
| `/vehiculo/{id_vehiculo}` | `GET` | `sp_obtener_demos` | Lista todas las secuencias DEMO asociadas a un vehículo. |
| `/` | `POST` | `sp_crear_demo` | Registra una nueva secuencia DEMO. |
| `/{id_demo}` | `PUT` | `sp_actualizar_demo` | Actualiza la información general de una DEMO. |
| `/{id_demo}` | `DELETE` | `sp_eliminar_demo` | Elimina una secuencia DEMO. |
| `/{id_demo}/movimientos` | `POST` | `sp_agregar_movimiento` | Agrega un nuevo paso (comando) a una DEMO existente. |
| `/{id_demo}/movimientos` | `GET` | `sp_obtener_movimientos` | Obtiene la lista ordenada de pasos de una DEMO. |
| `/movimientos/{id_mov}` | `PUT` | `sp_actualizar_movimiento` | Modifica la duración, pausa o comando de un paso. |
| `/movimientos/{id_mov}` | `DELETE` | `sp_eliminar_movimiento` | Elimina un paso específico de la secuencia. |
| `/{id_demo}/ejecutar` | `POST` | `sp_actualizar_estado` | Ejecuta la DEMO de forma asíncrona. Actualiza el estado del vehículo en RDS en cada iteración. |
| `/vehiculo/{id}/cancelar` | `POST` | `sp_actualizar_estado` | Cancela la ejecución asíncrona de emergencia y restablece el vehículo a estado Standby (comando 9). |

*(Nota para la evaluación: Todos los endpoints cuentan con validación de datos mediante Pydantic y manejo de excepciones HTTP para proteger la base de datos).*

---

## 2. Eventos y Mensajería en Tiempo Real (WebSockets)

La API proporciona comunicación bidireccional en tiempo real (WSS) para monitorear la ejecución de las secuencias DEMO y el estado del vehículo. 

* **URL de Conexión:** `wss://api-vehiculo-iot.duckdns.org/api/demos/ws/{id_vehiculo}`

El servidor emite los siguientes payloads en formato **JSON** dependiendo de la etapa de la demostración:

### A. Al conectar (`estado_inicial`)
Se dispara automáticamente en el momento que un cliente se suscribe al WebSocket. Consulta la base de datos y devuelve el último estado conocido del vehículo.

```json
{
  "tipo_evento": "estado_inicial",
  "vehiculo": 1,
  "datos": {
    "id_vehiculo": 1,
    "vehiculo": "Excavadora IoT",
    "id_comando": 2,
    "comando": "RETROCEDER",
    "codigo": 2,
    "conectado": 1,
    "fecha_actualizacion": "2026-10-18T04:06:40"
  }
}

```

### B. Al iniciar una secuencia (`inicio_demo`)

Se emite cuando se recibe una petición `POST` válida en el endpoint de ejecución.

```json
{
  "tipo_evento": "inicio_demo",
  "vehiculo": 1
}

```

### C. Durante la ejecución (`movimiento_demo`)

Se emite iterativamente por cada paso configurado en la secuencia de la base de datos, notificando qué comando exacto se está ejecutando en ese instante.

```json
{
  "tipo_evento": "movimiento_demo",
  "vehiculo": 1,
  "comando_en_ejecucion": 3,
  "accion": "ejecutando_paso",
  "orden": 2
}

```

### D. Freno de Emergencia (`cancelacion_demo`)

Se emite si un usuario hace un llamado al endpoint `/cancelar`. Interrumpe los movimientos inmediatamente y restablece el hardware.

```json
{
  "tipo_evento": "cancelacion_demo",
  "vehiculo": 1
}

```

### E. Finalización exitosa (`fin_demo`)

Se emite cuando la secuencia termina todos sus pasos de manera natural.

```json
{
  "tipo_evento": "fin_demo",
  "vehiculo": 1
}

```

