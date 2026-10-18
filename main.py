from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from app.database import db_manager
from app.routers import vehiculos, comandos, telemetria, demos

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
    title="🚜 API Control y Telemetría - Excavadora IoT",
    description="Documentación oficial de los endpoints REST y WebSockets para el control remoto y monitoreo del vehículo.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None  
)

# === RUTA PERSONALIZADA PARA CAMBIAR COLORES Y AGREGAR PIE DE PÁGINA ===
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    html_response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        swagger_css_url="https://cdn.jsdelivr.net/gh/Itz-fork/Fastapi-Swagger-UI-Dark/assets/swagger_ui_dark.min.css",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": -1,
            "docExpansion": "list",
            "tryItOutEnabled": True,
            "syntaxHighlight.theme": "obsidian"
        }
    )
    
    custom_css_and_footer = """
    <style>
        /* GET - Azul Claro (Cyan/Sky Blue) */
        .swagger-ui .opblock.opblock-get { background-color: rgba(0, 168, 255, 0.08) !important; border-color: #00a8ff !important; }
        .swagger-ui .opblock.opblock-get .opblock-summary-method { background: #00a8ff !important; color: #fff !important; }
        
        /* POST - Verde Esmeralda */
        .swagger-ui .opblock.opblock-post { background-color: rgba(0, 184, 148, 0.08) !important; border-color: #00b894 !important; }
        .swagger-ui .opblock.opblock-post .opblock-summary-method { background: #00b894 !important; color: #fff !important; }
        
        /* PUT - Naranja Puro */
        .swagger-ui .opblock.opblock-put { background-color: rgba(255, 140, 0, 0.08) !important; border-color: #ff8c00 !important; }
        .swagger-ui .opblock.opblock-put .opblock-summary-method { background: #ff8c00 !important; color: #fff !important; }
        
        /* DELETE - Rosa Vibrante */
        .swagger-ui .opblock.opblock-delete { background-color: rgba(232, 67, 147, 0.08) !important; border-color: #e84393 !important; }
        .swagger-ui .opblock.opblock-delete .opblock-summary-method { background: #e84393 !important; color: #fff !important; }

        /* --- CORRECCIÓN: Arreglo para que las rutas no salgan en vertical --- */
        .swagger-ui .opblock .opblock-summary {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
        }
        .swagger-ui .opblock .opblock-summary-path {
            white-space: nowrap !important;  /* <- Esto fuerza a que el texto se mantenga en una línea */
            word-break: normal !important;
            flex: 0 1 auto !important;
            padding-left: 10px !important;
            font-size: 15px !important;
            font-family: monospace !important;
        }
        .swagger-ui .opblock .opblock-summary-description {
            padding-left: 15px !important;
            flex: 1 1 auto !important;
            text-align: left !important;
        }

        /* Estilos del Footer adaptados a Modo Oscuro */
        #custom-footer {
            text-align: center;
            padding: 20px;
            margin-top: 40px;
            background-color: #1e1e1e;
            border-top: 1px solid #333;
            color: #d4d4d4;
            font-family: sans-serif;
            font-size: 14px;
            width: 100%;
        }
    </style>
    
    <div id="custom-footer">
        Desarrollado por: <strong>Cynthia Martínez García</strong>
    </div>
    """
    
    original_html = html_response.body.decode("utf-8")
    css_part = custom_css_and_footer.split('<div id="custom-footer">')[0]
    footer_part = '<div id="custom-footer">' + custom_css_and_footer.split('<div id="custom-footer">')[1]

    html_with_css = original_html.replace("</head>", css_part + "</head>")
    final_html = html_with_css.replace("</body>", footer_part + "</body>")
    
    return HTMLResponse(final_html)

@app.get("/health/db", tags=["Health Check"])
def health_db():
    is_connected = db_manager.test_connection()
    return {
        "rds_connected": is_connected,
        "database": "vehiculo_iot"
    }

# --- REGISTRO DE ROUTERS ---
app.include_router(vehiculos.router)
app.include_router(comandos.router)
app.include_router(telemetria.router)
app.include_router(demos.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)