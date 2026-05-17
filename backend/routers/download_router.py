"""
Router per il download dei file audio generati.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.config import AppConfig, VoiceCatalog, OutputFormatCatalog
from backend.routers.tts_router import get_job_manager
from backend.models.schemas import JobState, ConfigResponse

router = APIRouter(prefix="/api", tags=["download"])


@router.get("/download/{job_id}")
async def download_audiobook(job_id: str) -> FileResponse:
    """Scarica il file MP3 dell'audiolibro generato."""
    job_manager = get_job_manager()
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")

    if job.state != JobState.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job non completato. Stato: {job.state.value}",
        )

    if not job.output_path or not job.output_path.exists():
        raise HTTPException(
            status_code=500,
            detail="File audio non trovato sul server",
        )

    download_name = f"{job.file_name}_audiobook.mp3"

    return FileResponse(
        path=str(job.output_path),
        media_type="audio/mpeg",
        filename=download_name,
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"'
        },
    )


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Ritorna la configurazione corrente (voci, formati, stato API key)."""
    return ConfigResponse(
        api_key_configured=len(AppConfig.validate()) == 0,
        voices=VoiceCatalog.get_all(),
        output_formats=OutputFormatCatalog.get_all(),
        price_per_1m_chars=AppConfig.PRICE_PER_1M_CHARS,
    )
