from typing import List, Optional
from app.database import db_manager
from app.schemas.demo import DemoCreate, MovimientoDemoCreate

class DemoService:
    def obtener_demos(self) -> List[dict]:
        """Ejecuta: sp_obtener_demos"""
        return db_manager.execute_sp("sp_obtener_demos")

    def obtener_demo_id(self, id_demo: int) -> Optional[dict]:
        """Ejecuta: sp_obtener_demo_id"""
        resultados = db_manager.execute_sp("sp_obtener_demo_id", (id_demo,))
        return resultados[0] if resultados else None

    def crear_demo(self, demo: DemoCreate) -> dict:
        """Ejecuta: sp_crear_demo"""
        db_manager.execute_sp("sp_crear_demo", (demo.nombre_demo, demo.descripcion, demo.activo))
        todos = self.obtener_demos()
        return todos[-1] if todos else {}

    def eliminar_demo(self, id_demo: int) -> bool:
        """Ejecuta: sp_eliminar_demo"""
        db_manager.execute_sp("sp_eliminar_demo", (id_demo,))
        return True

    def agregar_movimiento(self, mov: MovimientoDemoCreate) -> bool:
        """Ejecuta: sp_agregar_movimiento_demo"""
        db_manager.execute_sp("sp_agregar_movimiento_demo", (
            mov.id_demo, mov.id_comando, mov.orden, mov.duracion_ms, mov.pausa_ms
        ))
        return True

    def obtener_movimientos(self, id_demo: int) -> List[dict]:
        """Ejecuta: sp_obtener_movimientos_demo"""
        return db_manager.execute_sp("sp_obtener_movimientos_demo", (id_demo,))

demo_service = DemoService()