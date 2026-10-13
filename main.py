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
    title="API Vehículo IoT - Práctica 2.5",
    description="API desarrollada con FastAPI, POO, WebSocket y Amazon RDS",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None  # Apagamos la ruta por defecto para poder inyectar colores y pie de página
)

# === RUTA PERSONALIZADA PARA CAMBIAR COLORES Y AGREGAR PIE DE PÁGINA ===
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    # 1. Generamos el HTML original de Swagger
    html_response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": -1,
            "docExpansion": "list",
            "tryItOutEnabled": True,
            "syntaxHighlight.theme": "obsidian"
        }
    )
    
    # 2. Creamos nuestros colores personalizados (CSS) actualizados
    custom_css_and_footer = """
    <style>
        /* GET - Azul Claro (Cyan/Sky Blue) */
        .swagger-ui .opblock.opblock-get { background-color: rgba(0, 168, 255, 0.08); border-color: #00a8ff; }
        .swagger-ui .opblock.opblock-get .opblock-summary-method { background: #00a8ff; color: #fff; }
        
        /* POST - Verde Esmeralda */
        .swagger-ui .opblock.opblock-post { background-color: rgba(0, 184, 148, 0.08); border-color: #00b894; }
        .swagger-ui .opblock.opblock-post .opblock-summary-method { background: #00b894; color: #fff; }
        
        /* PUT - Naranja Puro */
        .swagger-ui .opblock.opblock-put { background-color: rgba(255, 140, 0, 0.08); border-color: #ff8c00; }
        .swagger-ui .opblock.opblock-put .opblock-summary-method { background: #ff8c00; color: #fff; }
        
        /* DELETE - Rosa Vibrante */
        .swagger-ui .opblock.opblock-delete { background-color: rgba(232, 67, 147, 0.08); border-color: #e84393; }
        .swagger-ui .opblock.opblock-delete .opblock-summary-method { background: #e84393; color: #fff; }

        /* Estilos del Footer */
        #custom-footer {
            text-align: center;
            padding: 20px;
            margin-top: 40px;
            background-color: #f8f9fa;
            border-top: 1px solid #e9ecef;
            color: #495057;
            font-family: sans-serif;
            font-size: 14px;
            width: 100%;
        }
    </style>
    
    <div id="custom-footer">
        Desarrollado por: <strong>Cynthia Martínez García</strong>
    </div>
    """
    
    # 3. Inyectamos los colores CSS antes de cerrar <head> y el pie de página antes de cerrar <body>
    original_html = html_response.body.decode("utf-8")
    
    # Extraemos el bloque CSS de la variable anterior
    css_part = custom_css_and_footer.split('<div id="custom-footer">')[0]
    footer_part = '<div id="custom-footer">' + custom_css_and_footer.split('<div id="custom-footer">')[1]

    # Inyectamos CSS en Head
    html_with_css = original_html.replace("</head>", css_part + "</head>")
    
    # Inyectamos Footer en Body
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