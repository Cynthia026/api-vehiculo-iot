from fastapi import WebSocket
from typing import Dict, List
from fastapi.encoders import jsonable_encoder
from app.services.telemetria_service import telemetria_service

class ConnectionManager:
    """
    Gestor de conexiones WebSocket.
    Separa clientes por vehículo y envía el estado inicial al conectar (Rúbrica Punto 7).
    """
    def __init__(self):
        # Diccionario para separar conexiones: { id_vehiculo: [WebSocket, WebSocket] }
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, id_vehiculo: int):
        """Acepta una nueva conexión, la asigna a su vehículo y envía el último estado."""
        await websocket.accept()
        
        # Crear la lista para este vehículo si es el primero en conectarse
        if id_vehiculo not in self.active_connections:
            self.active_connections[id_vehiculo] = []
        self.active_connections[id_vehiculo].append(websocket)

        # --- REGLA DEL EXAMEN: Entregar estado guardado en RDS inmediatamente ---
        estado_actual = telemetria_service.obtener_estado(id_vehiculo)
        if estado_actual:
            mensaje_inicial = {
                "tipo_evento": "estado_inicial",
                "vehiculo": id_vehiculo,
                "datos": jsonable_encoder(estado_actual)
            }
            await websocket.send_json(mensaje_inicial)

    def disconnect(self, websocket: WebSocket, id_vehiculo: int):
        """Elimina la conexión específica del vehículo."""
        if id_vehiculo in self.active_connections:
            if websocket in self.active_connections[id_vehiculo]:
                self.active_connections[id_vehiculo].remove(websocket)
            # Liberar memoria si ya nadie escucha a este vehículo
            if not self.active_connections[id_vehiculo]:
                del self.active_connections[id_vehiculo]

    async def broadcast_json(self, message: dict):
        """Envía el mensaje SOLO a los clientes que observan al vehículo afectado."""
        # Extraemos el vehículo del mensaje de forma automática para no afectar tus otros archivos
        id_vehiculo = message.get("vehiculo")
        if not id_vehiculo and "datos" in message:
            id_vehiculo = message["datos"].get("id_vehiculo")

        # Enviamos el WSS solo a la "sala" correcta
        if id_vehiculo and id_vehiculo in self.active_connections:
            conexiones = self.active_connections[id_vehiculo]
        else:
            # Fallback por si el JSON no tiene ID (se envía a todos)
            conexiones = [ws for sublista in self.active_connections.values() for ws in sublista]
            
        for connection in conexiones:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WebSocket] Error enviando mensaje a cliente: {e}")

# Instancia global
ws_manager = ConnectionManager()