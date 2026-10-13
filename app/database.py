import pymysql
from pymysql.cursors import DictCursor
from typing import List, Optional
from app.config import settings

class DatabaseManager:
    """
    Clase encargada de administrar la conexión a Amazon RDS
    y estandarizar la ejecución de los 21 Stored Procedures.
    """
    def __init__(self):
        self._host = settings.DB_HOST
        self._port = settings.DB_PORT
        self._user = settings.DB_USER
        self._password = settings.DB_PASSWORD
        self._database = settings.DB_NAME

    def get_connection(self):
        """Retorna una conexión activa hacia Amazon RDS."""
        return pymysql.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
            cursorclass=DictCursor,
            autocommit=True
        )

    def test_connection(self) -> bool:
        """Comprueba conectividad activa con Amazon RDS."""
        try:
            connection = self.get_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS status;")
                result = cursor.fetchone()
            connection.close()
            return result is not None and result.get("status") == 1
        except Exception as error:
            print(f"[ERROR RDS] Conexión fallida: {error}")
            return False

    def execute_sp(self, procedure_name: str, params: Optional[tuple] = None) -> List[dict]:
        """
        Ejecuta un procedimiento almacenado vía CALL y retorna los registros.
        """
        connection = self.get_connection()
        try:
            with connection.cursor() as cursor:
                if params:
                    cursor.callproc(procedure_name, params)
                else:
                    cursor.callproc(procedure_name)
                result = cursor.fetchall()
                return list(result)
        finally:
            connection.close()

# Singleton para consumo de los servicios
db_manager = DatabaseManager()