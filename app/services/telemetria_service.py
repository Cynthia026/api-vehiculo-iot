from typing import Optional, List
from app.database import db_manager
from app.schemas.estado import EstadoVehiculoUpdate

class TelemetriaService:
    def actualizar_estado(self, estado: EstadoVehiculoUpdate) -> Optional[dict]:
        db_manager.execute_sp("sp_actualizar_estado", (
            estado.id_vehiculo, estado.id_comando, estado.conectado
        ))
        return self.obtener_estado(estado.id_vehiculo)

    def obtener_estado(self, id_vehiculo: int) -> Optional[dict]:
        resultados = db_manager.execute_sp("sp_obtener_estado", (id_vehiculo,))
        return resultados[0] if resultados else None

telemetria_service = TelemetriaService()
