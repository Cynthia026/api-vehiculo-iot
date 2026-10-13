from typing import List, Optional
from app.database import db_manager
from app.schemas.demo import DemoCreate, DemoUpdate, MovimientoDemoCreate, MovimientoDemoUpdate

class DemoService:
    def obtener_demos(self, id_vehiculo: int) -> List[dict]:
        return db_manager.execute_sp("sp_obtener_demos", (id_vehiculo,))

    def crear_demo(self, demo: DemoCreate) -> dict:
        db_manager.execute_sp("sp_crear_demo", (demo.id_vehiculo, demo.nombre, demo.descripcion))
        todos = self.obtener_demos(demo.id_vehiculo)
        return todos[-1] if todos else {}
        
    def actualizar_demo(self, id_demo: int, demo: DemoUpdate) -> bool:
        db_manager.execute_sp("sp_actualizar_demo", (id_demo, demo.nombre, demo.descripcion, demo.activo))
        return True

    def eliminar_demo(self, id_demo: int) -> bool:
        db_manager.execute_sp("sp_eliminar_demo", (id_demo,))
        return True

    def agregar_movimiento(self, mov: MovimientoDemoCreate) -> bool:
        db_manager.execute_sp("sp_agregar_movimiento_demo", (
            mov.id_demo, mov.id_comando, mov.orden, mov.duracion_ms, mov.pausa_ms
        ))
        return True

    def obtener_movimientos(self, id_demo: int) -> List[dict]:
        return db_manager.execute_sp("sp_obtener_movimientos_demo", (id_demo,))

    def actualizar_movimiento(self, id_demo_movimiento: int, mov: MovimientoDemoUpdate) -> bool:
        db_manager.execute_sp("sp_actualizar_movimiento_demo", (
            id_demo_movimiento, mov.id_comando, mov.orden, mov.duracion_ms, mov.pausa_ms
        ))
        return True

    def eliminar_movimiento(self, id_demo_movimiento: int) -> bool:
        db_manager.execute_sp("sp_eliminar_movimiento_demo", (id_demo_movimiento,))
        return True

demo_service = DemoService()
