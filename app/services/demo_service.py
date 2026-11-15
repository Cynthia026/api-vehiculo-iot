from typing import Any, List, Optional
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
        filas = db_manager.execute_sp("sp_obtener_movimientos_demo", (id_demo,))
        return [self._normalizar_movimiento(f, id_demo, i) for i, f in enumerate(filas or [])]

    @staticmethod
    def _a_int(valor: Any, defecto: Optional[int] = None) -> Optional[int]:
        try:
            return int(valor)
        except (TypeError, ValueError):
            return defecto

    def _normalizar_movimiento(self, fila: dict, id_demo: int, indice: int) -> dict:
        """
        Adapta cada fila del SP al formato de MovimientoDemoResponse.
        El SP puede omitir id_demo, nombrar distinto el id del paso o el nombre del comando,
        o devolver 'codigo' como texto; antes eso provocaba un error 500 al validar la respuesta.
        """
        fila = dict(fila or {})
        id_paso = fila.get("id_demo_movimiento")
        if id_paso is None:
            for clave in ("id_movimiento_demo", "id_movimiento", "id"):
                if fila.get(clave) is not None:
                    id_paso = fila[clave]
                    break
        return {
            "id_demo_movimiento": self._a_int(id_paso),
            "id_demo": self._a_int(fila.get("id_demo"), id_demo),
            "id_comando": self._a_int(fila.get("id_comando")),
            "orden": self._a_int(fila.get("orden"), indice + 1),
            "duracion_ms": self._a_int(fila.get("duracion_ms"), 1000),
            "pausa_ms": self._a_int(fila.get("pausa_ms"), 0),
            "comando": fila.get("comando") or fila.get("nombre_comando") or fila.get("nombre"),
            "codigo": self._a_int(fila.get("codigo")),
        }

    def actualizar_movimiento(self, id_demo_movimiento: int, mov: MovimientoDemoUpdate) -> bool:
        db_manager.execute_sp("sp_actualizar_movimiento_demo", (
            id_demo_movimiento, mov.id_comando, mov.orden, mov.duracion_ms, mov.pausa_ms
        ))
        return True

    def eliminar_movimiento(self, id_demo_movimiento: int) -> bool:
        db_manager.execute_sp("sp_eliminar_movimiento_demo", (id_demo_movimiento,))
        return True

demo_service = DemoService()
