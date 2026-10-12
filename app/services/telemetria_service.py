from typing import Optional, List
from app.database import db_manager
from app.schemas.estado import EstadoVehiculoUpdate

class TelemetriaService:
    def actualizar_estado(self, estado: EstadoVehiculoUpdate) -> Optional[dict]:
        """Ejecuta: sp_actualizar_estado"""
        db_manager.execute_sp("sp_actualizar_estado", (
            estado.id_vehiculo, estado.estado, estado.velocidad, 
            estado.bateria, estado.orientacion, estado.conexion_activa
        ))
        return self.obtener_estado(estado.id_vehiculo)

    def obtener_estado(self, id_vehiculo: int) -> Optional[dict]:
        """Ejecuta: sp_obtener_estado_vehiculo"""
        resultados = db_manager.execute_sp("sp_obtener_estado_vehiculo", (id_vehiculo,))
        return resultados[0] if resultados else None

telemetria_service = TelemetriaService()