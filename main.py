from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import db_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n=======================================================")
    print(" Verificando conexión a Amazon RDS (vehiculo_iot)...")
    if db_manager.test_connection():
        print(" [OK] Conexión establecida exitosamente con Amazon RDS.")
    else:
        print(" [ADVERTENCIA] No se pudo conectar a RDS.")
        print(" -> Revisa tu archivo .env y el Security Group (puerto 3306).")
    print("=======================================================\n")
    yield
    print("\n--- Servidor detenido. ---")

app = FastAPI(
    title="API Vehículo IoT - Práctica 2.5",
    description="API desarrollada con FastAPI, POO, WebSocket y Amazon RDS",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/", tags=["Health Check"])
def root():
    """Endpoint raíz para verificación operativa del servidor."""
    return {
        "status": "online",
        "practica": "2.5",
        "entorno": "local",
        "puerto": 8000
    }

@app.get("/health/db", tags=["Health Check"])
def health_db():
    """Valida la conectividad directa con Amazon RDS."""
    is_connected = db_manager.test_connection()
    return {
        "rds_connected": is_connected,
        "database": "vehiculo_iot"
    }