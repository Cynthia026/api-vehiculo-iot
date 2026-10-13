from typing import List, Optional
from app.database import db_manager
from app.schemas.vehiculo import VehiculoCreate, VehiculoUpdate

class VehiculoService:
    def obtener_todos(self) -> List[dict]:
        return db_manager.execute_sp("sp_obtener_vehiculos")

    def obtener_por_id(self, id_vehiculo: int) -> Optional[dict]:
        resultados = db_manager.execute_sp("sp_obtener_vehiculo", (id_vehiculo,))
        return resultados[0] if resultados else None

    def crear(self, vehiculo: VehiculoCreate) -> dict:
        db_manager.execute_sp("sp_crear_vehiculo", (
            vehiculo.nombre, vehiculo.modelo, vehiculo.descripcion, vehiculo.microcontrolador
        ))
        todos = self.obtener_todos()
        return todos[-1] if todos else {}

    def actualizar(self, id_vehiculo: int, vehiculo: VehiculoUpdate) -> Optional[dict]:
        db_manager.execute_sp("sp_actualizar_vehiculo", (
            id_vehiculo, vehiculo.nombre, vehiculo.modelo,
            vehiculo.descripcion, vehiculo.microcontrolador, vehiculo.activo
        ))
        return self.obtener_por_id(id_vehiculo)

    def eliminar(self, id_vehiculo: int) -> bool:
        db_manager.execute_sp("sp_eliminar_vehiculo", (id_vehiculo,))
        return True

vehiculo_service = VehiculoService()
