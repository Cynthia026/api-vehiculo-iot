from typing import List
from app.database import db_manager
from app.schemas.historial import HistorialCreate

class HistorialService:
    def registrar_movimiento(self, historial: HistorialCreate) -> dict:
        """Ejecuta: sp_registrar_historial"""
        db_manager.execute_sp("sp_registrar_historial", (
            historial.id_vehiculo, historial.id_comando, historial.detalles
        ))
        registros = self.obtener_historial(historial.id_vehiculo)
        return registros[0] if registros else {}

    def obtener_historial(self, id_vehiculo: int) -> List[dict]:
        """Ejecuta: sp_obtener_historial_vehiculo (Devuelve los últimos 10)"""
        return db_manager.execute_sp("sp_obtener_historial_vehiculo", (id_vehiculo,))

    def limpiar_historial(self, id_vehiculo: int) -> bool:
        """Ejecuta: sp_limpiar_historial_vehiculo"""
        db_manager.execute_sp("sp_limpiar_historial_vehiculo", (id_vehiculo,))
        return True

historial_service = HistorialService()