from typing import List, Optional
from app.database import db_manager
from app.schemas.vehiculo import VehiculoCreate, VehiculoUpdate

class VehiculoService:
    """Servicio POO para administrar el catálogo de vehículos IoT."""
    
    def obtener_todos(self) -> List[dict]:
        """Ejecuta: sp_obtener_vehiculos"""
        return db_manager.execute_sp("sp_obtener_vehiculos")

    def obtener_por_id(self, id_vehiculo: int) -> Optional[dict]:
        """Ejecuta: sp_obtener_vehiculo_id"""
        resultados = db_manager.execute_sp("sp_obtener_vehiculo_id", (id_vehiculo,))
        return resultados[0] if resultados else None

    def crear(self, vehiculo: VehiculoCreate) -> dict:
        """Ejecuta: sp_crear_vehiculo"""
        db_manager.execute_sp("sp_crear_vehiculo", (
            vehiculo.nombre, 
            vehiculo.descripcion, 
            vehiculo.activo
        ))
        # Para retornar el creado, idealmente el SP hace el SELECT o buscamos el último
        # Aquí consultamos los vehículos y devolvemos el último insertado por simplicidad
        todos = self.obtener_todos()
        return todos[-1] if todos else {}

    def actualizar(self, id_vehiculo: int, vehiculo: VehiculoUpdate) -> Optional[dict]:
        """Ejecuta: sp_actualizar_vehiculo"""
        actual = self.obtener_por_id(id_vehiculo)
        if not actual:
            return None
        
        # Mantenemos valores actuales si el update no los proporciona
        nombre_nuevo = vehiculo.nombre if vehiculo.nombre is not None else actual["nombre"]
        desc_nueva = vehiculo.descripcion if vehiculo.descripcion is not None else actual["descripcion"]
        activo_nuevo = vehiculo.activo if vehiculo.activo is not None else actual["activo"]

        db_manager.execute_sp("sp_actualizar_vehiculo", (
            id_vehiculo, nombre_nuevo, desc_nueva, activo_nuevo
        ))
        return self.obtener_por_id(id_vehiculo)

    def eliminar(self, id_vehiculo: int) -> bool:
        """Ejecuta: sp_eliminar_vehiculo"""
        if not self.obtener_por_id(id_vehiculo):
            return False
        db_manager.execute_sp("sp_eliminar_vehiculo", (id_vehiculo,))
        return True

vehiculo_service = VehiculoService()