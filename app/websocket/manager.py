from fastapi import WebSocket
from typing import List

class ConnectionManager:
    """
    Gestor de conexiones WebSocket.
    Mantiene la lista de clientes conectados y permite transmitir mensajes en tiempo real.
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Acepta una nueva conexión y la guarda en la lista."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Elimina la conexión cuando un cliente se desconecta."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_json(self, message: dict):
        """Envía un mensaje JSON a todos los clientes conectados simultáneamente."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WebSocket] Error enviando mensaje a cliente: {e}")

# Instancia global para usar en todos los endpoints
ws_manager = ConnectionManager()