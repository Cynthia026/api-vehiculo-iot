from typing import List
from app.database import db_manager
from app.schemas.historial import HistorialCreate

class HistorialService:
    def registrar_movimiento(self, historial: HistorialCreate) -> dict:
        db_manager.execute_sp("sp_registrar_historial", (
            historial.id_vehiculo, historial.id_comando, historial.origen
        ))
        registros = self.obtener_historial(historial.id_vehiculo)
        return registros[0] if registros else {}

    def obtener_historial(self, id_vehiculo: int) -> List[dict]:
        return db_manager.execute_sp("sp_obtener_historial", (id_vehiculo,))

historial_service = HistorialService()
