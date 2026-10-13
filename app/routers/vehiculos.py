from fastapi import APIRouter, HTTPException, status
from typing import List
from app.schemas.vehiculo import VehiculoCreate, VehiculoUpdate, VehiculoResponse
from app.services.vehiculo_service import vehiculo_service

router = APIRouter(prefix="/api/vehiculos", tags=["Vehículos"])

@router.get("/", response_model=List[VehiculoResponse])
def listar_vehiculos():
    """Consulta todos los vehículos registrados."""
    return vehiculo_service.obtener_todos()

@router.get("/{id_vehiculo}", response_model=VehiculoResponse)
def obtener_vehiculo(id_vehiculo: int):
    """Consulta un vehículo específico por su ID."""
    vehiculo = vehiculo_service.obtener_por_id(id_vehiculo)
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return vehiculo

@router.post("/", response_model=VehiculoResponse, status_code=status.HTTP_201_CREATED)
def crear_vehiculo(vehiculo: VehiculoCreate):
    """Registra un nuevo vehículo en la base de datos."""
    return vehiculo_service.crear(vehiculo)

@router.put("/{id_vehiculo}", response_model=VehiculoResponse)
def actualizar_vehiculo(id_vehiculo: int, vehiculo: VehiculoUpdate):
    """Actualiza los datos de un vehículo existente."""
    actualizado = vehiculo_service.actualizar(id_vehiculo, vehiculo)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return actualizado

@router.delete("/{id_vehiculo}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_vehiculo(id_vehiculo: int):
    """Elimina un vehículo del sistema."""
    if not vehiculo_service.eliminar(id_vehiculo):
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return None