"""
Router per controllare lo stato dei job di generazione.
"""

from fastapi import APIRouter, HTTPException

from backend.routers.tts_router import get_job_manager
from backend.models.schemas import JobStatusResponse

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Ritorna lo stato corrente di un job."""
    job_manager = get_job_manager()
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")

    return JobStatusResponse(
        job_id=job.job_id,
        state=job.state,
        progress_percent=round(job.progress_percent, 1),
        chunks_total=job.chunks_total,
        chunks_completed=job.chunks_completed,
        error_message=job.error_message,
        file_name=job.file_name,
    )


@router.get("/jobs")
async def list_jobs() -> list[dict]:
    """Lista tutti i job attivi e completati."""
    job_manager = get_job_manager()
    return job_manager.list_jobs()
