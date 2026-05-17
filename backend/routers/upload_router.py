"""
Router per l'upload dei file di testo.
Gestisce caricamento, validazione e anteprima.
"""

import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, HTTPException

from backend.config import AppConfig
from backend.managers.text_splitter import TextSplitter
from backend.models.schemas import UploadResponse

logger = logging.getLogger("davetts.upload")
router = APIRouter(prefix="/api", tags=["upload"])

ALLOWED_EXTENSIONS = {".txt"}
MAX_SIZE_BYTES = AppConfig.MAX_UPLOAD_SIZE_MB * 1024 * 1024

text_splitter = TextSplitter(AppConfig.MAX_CHUNK_SIZE)


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile) -> UploadResponse:
    """
    Carica un file .txt per la generazione dell'audiolibro.
    Ritorna metadati e stima dei chunk.
    """
    _validate_file(file)

    content = await file.read()

    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File troppo grande. Massimo {AppConfig.MAX_UPLOAD_SIZE_MB}MB",
        )

    text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Il file è vuoto",
        )

    file_id = uuid.uuid4().hex[:12]
    file_name = file.filename or f"{file_id}.txt"
    save_path = AppConfig.UPLOADS_DIR / f"{file_id}.txt"

    AppConfig.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    save_path.write_text(text, encoding="utf-8")

    estimated_chunks = text_splitter.estimate_chunks(text)

    logger.info(
        "File caricato: '%s' (%d caratteri, ~%d chunk) -> %s",
        file_name, len(text), estimated_chunks, file_id,
    )

    return UploadResponse(
        file_id=file_id,
        file_name=file_name,
        text_length=len(text),
        estimated_chunks=estimated_chunks,
    )


@router.get("/preview/{file_id}")
async def preview_file(file_id: str) -> dict:
    """Ritorna un'anteprima del testo caricato (prime 2000 caratteri)."""
    file_path = AppConfig.UPLOADS_DIR / f"{file_id}.txt"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File non trovato")

    text = file_path.read_text(encoding="utf-8")
    preview = text[:2000]
    is_truncated = len(text) > 2000

    return {
        "file_id": file_id,
        "preview": preview,
        "is_truncated": is_truncated,
        "total_length": len(text),
    }


def _validate_file(file: UploadFile):
    """Valida tipo e nome del file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome file mancante")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato non supportato: {suffix}. Usa: {ALLOWED_EXTENSIONS}",
        )
