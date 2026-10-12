from typing import List, Optional
from app.database import db_manager
from app.schemas.comando import ComandoCreate, ComandoUpdate

class ComandoService:
    """Servicio POO para administrar las instrucciones operativas de los vehículos."""
    
    def obtener_todos(self) -> List[dict]:
        """Ejecuta: sp_obtener_comandos"""
        return db_manager.execute_sp("sp_obtener_comandos")

    def obtener_por_id(self, id_comando: int) -> Optional[dict]:
        """Ejecuta: sp_obtener_comando_id"""
        resultados = db_manager.execute_sp("sp_obtener_comando_id", (id_comando,))
        return resultados[0] if resultados else None

    def crear(self, comando: ComandoCreate) -> dict:
        """Ejecuta: sp_crear_comando"""
        db_manager.execute_sp("sp_crear_comando", (
            comando.id_vehiculo, 
            comando.nombre_comando, 
            comando.instruccion_hex, 
            comando.activo
        ))
        todos = self.obtener_todos()
        return todos[-1] if todos else {}

    def actualizar(self, id_comando: int, comando: ComandoUpdate) -> Optional[dict]:
        """Ejecuta: sp_actualizar_comando"""
        actual = self.obtener_por_id(id_comando)
        if not actual:
            return None
            
        nombre_nuevo = comando.nombre_comando if comando.nombre_comando is not None else actual["nombre_comando"]
        hex_nuevo = comando.instruccion_hex if comando.instruccion_hex is not None else actual["instruccion_hex"]
        activo_nuevo = comando.activo if comando.activo is not None else actual["activo"]

        db_manager.execute_sp("sp_actualizar_comando", (
            id_comando, nombre_nuevo, hex_nuevo, activo_nuevo
        ))
        return self.obtener_por_id(id_comando)

    def eliminar(self, id_comando: int) -> bool:
        """Ejecuta: sp_eliminar_comando"""
        if not self.obtener_por_id(id_comando):
            return False
        db_manager.execute_sp("sp_eliminar_comando", (id_comando,))
        return True

comando_service = ComandoService()