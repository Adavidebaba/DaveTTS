"""
Entry point dell'applicazione DaveTTS.
Configura FastAPI, monta file statici e include i router.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import AppConfig
from backend.routers import upload_router, tts_router, status_router, download_router

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("davetts")

# Creazione app FastAPI
app = FastAPI(
    title="DaveTTS",
    description="Generatore di audiolibri con xAI TTS",
    version="1.0.0",
)

# Creazione directory dati
AppConfig.ensure_directories()

# Inclusione router API
app.include_router(upload_router.router)
app.include_router(tts_router.router)
app.include_router(status_router.router)
app.include_router(download_router.router)

# Mount file statici del frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount(
    "/css",
    StaticFiles(directory=str(FRONTEND_DIR / "css")),
    name="css",
)
app.mount(
    "/js",
    StaticFiles(directory=str(FRONTEND_DIR / "js")),
    name="js",
)


@app.get("/")
async def serve_index() -> FileResponse:
    """Serve la pagina principale."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.on_event("startup")
async def startup_event():
    """Log di avvio con stato configurazione."""
    provider = AppConfig.TTS_PROVIDER
    errors = AppConfig.validate(provider)
    if errors:
        logger.warning("⚠️  Problemi di configurazione: %s", errors)
    else:
        logger.info(
            "✅ Provider TTS '%s' configurato correttamente",
            provider,
        )

    logger.info(
        "🏛️  DaveTTS avviato su http://%s:%d",
        AppConfig.HOST, AppConfig.PORT,
    )
