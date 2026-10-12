import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Carga de variables de entorno desde .env
load_dotenv()

class Settings(BaseSettings):
    """
    Clase de configuración POO que encapsula las variables de entorno
    para la conexión a RDS y el servidor FastAPI.
    """
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 3306))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "vehiculo_iot")
    
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", 8000))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()