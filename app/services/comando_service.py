from typing import List, Optional
from app.database import db_manager
from app.schemas.comando import ComandoCreate, ComandoUpdate

class ComandoService:
    def obtener_comandos_vehiculo(self, id_vehiculo: int) -> List[dict]:
        return db_manager.execute_sp("sp_obtener_comandos_vehiculo", (id_vehiculo,))

    def crear(self, comando: ComandoCreate) -> dict:
        db_manager.execute_sp("sp_crear_comando", (
            comando.id_vehiculo, comando.nombre, comando.codigo, comando.descripcion
        ))
        todos = self.obtener_comandos_vehiculo(comando.id_vehiculo)
        return todos[-1] if todos else {}

    def actualizar(self, id_comando: int, comando: ComandoUpdate) -> bool:
        db_manager.execute_sp("sp_actualizar_comando", (
            id_comando, comando.nombre, comando.codigo, comando.descripcion, comando.activo
        ))
        return True

    def eliminar(self, id_comando: int) -> bool:
        db_manager.execute_sp("sp_eliminar_comando", (id_comando,))
        return True

comando_service = ComandoService()
