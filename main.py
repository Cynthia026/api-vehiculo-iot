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

# QUITAMOS EL CARRITO DE AQUÍ PARA INYECTARLO CON CSS
app = FastAPI(
    title="API Control y Telemetría - Excavadora IoT",
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
        swagger_ui_parameters={
            "defaultModelsExpandDepth": -1,
            "docExpansion": "none", 
            "tryItOutEnabled": True
        }
    )
    
    custom_css_and_footer = """
    <style>
        /* --- FONDO ROSA MUY SUTIL Y ELEGANTE --- */
        body, .swagger-ui {
            background-color: #fcf0f4 !important; 
        }
        .swagger-ui .scheme-container {
            background-color: #fae6ec !important; 
            box-shadow: none !important;
            border-bottom: 2px solid #f8d0db !important;
        }

        /* --- CENTRAR EL TÍTULO Y LA DESCRIPCIÓN --- */
        .swagger-ui .info {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            text-align: center !important;
            margin-top: 40px !important;
        }
        
        .swagger-ui .info .title {
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            width: 100% !important;
            flex-wrap: wrap !important;
        }
        
        /* MAGIA CSS: Inyectamos el carrito magenta */
        .swagger-ui .info .title::before {
            content: "🚜";
            display: inline-block;
            margin-right: 12px;
            font-size: 1.1em;
            filter: hue-rotate(200deg) saturate(3) brightness(1.1);
        }

        .swagger-ui .info .description {
            text-align: center !important;
            margin: 0 auto !important;
            max-width: 800px !important;
        }
        .swagger-ui .info .base-url {
            display: flex !important;
            justify-content: center !important;
            width: 100% !important;
        }

        /* COLORES DE LOS MÉTODOS HTTP */
        .swagger-ui .opblock.opblock-get { background-color: rgba(0, 168, 255, 0.08) !important; border-color: #00a8ff !important; }
        .swagger-ui .opblock.opblock-get .opblock-summary-method { background: #00a8ff !important; color: #fff !important; }
        
        .swagger-ui .opblock.opblock-post { background-color: rgba(0, 184, 148, 0.08) !important; border-color: #00b894 !important; }
        .swagger-ui .opblock.opblock-post .opblock-summary-method { background: #00b894 !important; color: #fff !important; }
        
        .swagger-ui .opblock.opblock-put { background-color: rgba(255, 140, 0, 0.08) !important; border-color: #ff8c00 !important; }
        .swagger-ui .opblock.opblock-put .opblock-summary-method { background: #ff8c00 !important; color: #fff !important; }
        
        .swagger-ui .opblock.opblock-delete { background-color: rgba(232, 67, 147, 0.08) !important; border-color: #e84393 !important; }
        .swagger-ui .opblock.opblock-delete .opblock-summary-method { background: #e84393 !important; color: #fff !important; }

        /* --- RUTAS HORIZONTALES --- */
        .swagger-ui .opblock-summary {
            display: flex !important;
            align-items: center !important;
            flex-wrap: nowrap !important;
        }
        .swagger-ui .opblock-summary-path,
        .swagger-ui .opblock-summary-path a {
            white-space: nowrap !important;
            word-break: keep-all !important;
            font-size: 15px !important;
            display: inline-block !important; 
            padding-right: 15px !important;
            color: #333 !important;
        }

        /* --- TÍTULOS PRINCIPALES Y ALINEACIÓN --- */
        .swagger-ui .opblock-tag {
            color: #d81b60 !important; 
            font-size: 22px !important;
            border-bottom: 2px solid rgba(216, 27, 96, 0.2) !important;
            font-weight: bold !important;
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important; 
        }
        
        .swagger-ui .opblock-tag > div:first-child {
            display: flex !important;
            align-items: center !important;
        }

        .swagger-ui .opblock-tag svg {
            fill: #d81b60 !important; 
        }

        /* --- FOOTER --- */
        #custom-footer {
            text-align: center;
            padding: 20px;
            margin-top: 40px;
            background-color: #fae6ec; 
            border-top: 1px solid #f8d0db;
            color: #495057;
            font-family: sans-serif;
            font-size: 14px;
            width: 100%;
        }
    </style>
    
    <div id="custom-footer">
        Desarrollado por: <strong>Cynthia Martínez García</strong>
    </div>

    <!-- SCRIPT CORREGIDO PARA LOS CONTADORES -->
    <script>
        setInterval(() => {
            const sections = document.querySelectorAll('.swagger-ui .opblock-tag-section');
            
            sections.forEach(section => {
                const titleEl = section.querySelector('.opblock-tag');
                const count = section.querySelectorAll('.opblock').length;
                
                if (titleEl && count > 0 && !titleEl.hasAttribute('data-counted')) {
                    const badge = document.createElement('span');
                    badge.style.backgroundColor = '#d81b60';
                    badge.style.color = '#ffffff';
                    badge.style.borderRadius = '12px';
                    badge.style.padding = '4px 12px';
                    badge.style.marginLeft = '15px';
                    badge.style.fontSize = '13px';
                    badge.style.fontWeight = 'bold';
                    badge.innerText = count + (count === 1 ? ' Endpoint' : ' Endpoints');
                    
                    const linkEl = titleEl.querySelector('a');
                    if (linkEl) {
                        linkEl.parentNode.insertBefore(badge, linkEl.nextSibling);
                    }
                    
                    titleEl.setAttribute('data-counted', 'true');
                }
            });
        }, 1000); 
    </script>
    """
    
    original_html = html_response.body.decode("utf-8")
    css_part = custom_css_and_footer.split('<div id="custom-footer">')[0]
    footer_and_script = '<div id="custom-footer">' + custom_css_and_footer.split('<div id="custom-footer">')[1]

    html_with_css = original_html.replace("</head>", css_part + "</head>")
    final_html = html_with_css.replace("</body>", footer_and_script + "</body>")
    
    return HTMLResponse(final_html)


# --- REGISTRO DE ROUTERS ---
app.include_router(vehiculos.router)
app.include_router(comandos.router)
app.include_router(telemetria.router)
app.include_router(demos.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)