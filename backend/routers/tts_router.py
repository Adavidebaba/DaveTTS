"""
Router per la generazione TTS degli audiolibri.
Gestisce avvio generazione asincrona in background.
"""

import logging
import hashlib

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.config import AppConfig, OutputFormatCatalog
from backend.voice_catalog import get_voice_catalog
from backend.managers.text_splitter import TextSplitter
from backend.managers.tts_provider import create_tts_client, get_error_classes
from backend.managers.audio_merger import AudioMerger
from backend.managers.chunk_storage import ChunkStorage
from backend.managers.job_manager import JobManager, Job
from backend.models.schemas import GenerateRequest, JobState

logger = logging.getLogger("davetts.tts_router")
router = APIRouter(prefix="/api", tags=["tts"])

# Istanze condivise (singleton a livello di modulo)
job_manager = JobManager()
text_splitter = TextSplitter(AppConfig.MAX_CHUNK_SIZE)
audio_merger = AudioMerger(AppConfig.PAUSE_BETWEEN_CHUNKS_MS)
chunk_storage = ChunkStorage()


def get_job_manager() -> JobManager:
    """Accessor per il job_manager condiviso (usato da altri router)."""
    return job_manager


@router.post("/generate")
async def start_generation(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Avvia la generazione dell'audiolibro in background.
    Ritorna immediatamente il job_id per il polling dello stato.
    """
    provider = request.provider

    # Validazione API key per il provider scelto
    config_errors = AppConfig.validate(provider)
    if config_errors:
        raise HTTPException(status_code=500, detail=config_errors[0])

    # Validazione voce
    voice_catalog = get_voice_catalog(provider)
    if not voice_catalog.is_valid(request.voice_id):
        raise HTTPException(
            status_code=400,
            detail=f"Voce '{request.voice_id}' non valida per {provider}",
        )

    # Verifica file esiste
    file_path = AppConfig.UPLOADS_DIR / f"{request.file_id}.txt"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File non trovato")

    # Il job_id ora coincide esattamente con il file_id come richiesto dall'utente
    job_id = request.file_id

    job = job_manager.get_job(job_id)

    if job:
        # Se il job esiste e sta ancora elaborando, non facciamo nulla e restituiamo l'id
        if job.state in (JobState.PENDING, JobState.SPLITTING, JobState.GENERATING, JobState.MERGING, JobState.COMPLETED, JobState.REVIEW):
            logger.info("Job %s già esistente in stato %s. Recupero.", job_id, job.state.value)
            return {
                "job_id": job.job_id,
                "message": "Generazione recuperata",
            }
        
        # Se il job esiste ma è in pausa/errore/cancellato, riprendiamolo automaticamente
        if job.state in (JobState.PAUSED, JobState.ERROR, JobState.CANCELLED, JobState.WAITING_QUOTA):
            logger.info("Job %s esistente in stato %s. Aggiornamento parametri e ripresa.", job_id, job.state.value)
            
            # Aggiorna i parametri con quelli nuovi inviati dal frontend
            job_manager.set_generation_params(
                job_id=job_id,
                voice_id=request.voice_id,
                language=request.language,
                output_format_id=request.output_format,
                text_chunks=job.text_chunks,
                provider=provider,
                prompt_data=request.prompt_data.model_dump() if request.prompt_data else None,
            )

            if job_manager.try_set_generating(job_id):
                background_tasks.add_task(_run_resume_pipeline, job=job)
            return {
                "job_id": job.job_id,
                "message": "Generazione ripresa con i nuovi parametri",
            }

    # Crea nuovo job
    job = job_manager.create_job(
        file_name=file_path.stem,
        file_path=file_path,
        job_id=job_id,
    )

    # Avvia generazione in background
    background_tasks.add_task(
        _run_generation_pipeline,
        job=job,
        voice_id=request.voice_id,
        language=request.language,
        output_format_id=request.output_format,
        provider=provider,
        prompt_data=request.prompt_data.model_dump() if request.prompt_data else None,
        preview_only=request.preview_only,
    )

    return {
        "job_id": job.job_id,
        "message": "Generazione avviata",
    }


@router.post("/resume/{job_id}")
async def resume_generation(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Riprende una generazione interrotta dal punto in cui si era fermata.
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")

    if job.state not in (JobState.PAUSED, JobState.ERROR, JobState.REVIEW):
        raise HTTPException(
            status_code=400,
            detail=f"Il job è in stato '{job.state.value}', "
                   f"non può essere ripreso",
        )

    if not job.text_chunks:
        raise HTTPException(
            status_code=400,
            detail="Dati di generazione mancanti, avvia un nuovo job",
        )

    # Validazione API key per il provider del job
    config_errors = AppConfig.validate(job.provider)
    if config_errors:
        raise HTTPException(status_code=500, detail=config_errors[0])

    # Reset stato per la ripresa
    if not job_manager.try_set_generating(job_id):
        raise HTTPException(
            status_code=400,
            detail="Generazione già in corso.",
        )

    background_tasks.add_task(
        _run_resume_pipeline,
        job=job,
    )

    return {
        "job_id": job.job_id,
        "message": "Generazione ripresa",
    }


@router.post("/cancel/{job_id}")
async def cancel_generation(job_id: str) -> dict:
    """Interrompe una generazione in corso."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")

    if job.state in (JobState.PENDING, JobState.SPLITTING, JobState.GENERATING, JobState.MERGING):
        job_manager.set_cancelled(job_id, "Generazione interrotta dall'utente.")
        return {"message": "Generazione interrotta"}
    
    raise HTTPException(
        status_code=400,
        detail=f"Impossibile interrompere job in stato '{job.state.value}'",
    )


from fastapi.responses import FileResponse

@router.get("/audio_preview/{job_id}")
async def get_audio_preview(job_id: str):
    """Restituisce il file MP3 del primo chunk per l'anteprima."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    
    chunk_path = chunk_storage.get_chunk_path(job_id, 0)
    if not chunk_path.exists():
        raise HTTPException(status_code=404, detail="Anteprima non trovata")
        
    return FileResponse(
        chunk_path,
        media_type="audio/mpeg",
        filename=f"preview_{job_id}.mp3"
    )


async def _run_generation_pipeline(
    job: Job,
    voice_id: str,
    language: str,
    output_format_id: str,
    provider: str,
    prompt_data: dict | None = None,
    preview_only: bool = False,
):
    """Pipeline completa: split → TTS → merge."""
    tts_error_cls, credit_error_cls = get_error_classes(provider)

    try:
        # FASE 1: Split testo
        job_manager.update_state(job.job_id, JobState.SPLITTING)
        text = job.file_path.read_text(encoding="utf-8")
        chunks = text_splitter.split(text)
        job_manager.set_chunks_total(job.job_id, len(chunks))

        # Salva parametri per eventuale ripresa
        job_manager.set_generation_params(
            job.job_id, voice_id, language,
            output_format_id, chunks, provider,
            prompt_data,
        )

        logger.info(
            "Job %s [%s]: testo diviso in %d chunk",
            job.job_id, provider, len(chunks),
        )

        # FASE 2: Generazione TTS con salvataggio progressivo
        job_manager.update_state(job.job_id, JobState.GENERATING)
        tts_client = create_tts_client(provider)

        def on_chunk_done(index: int, audio_bytes: bytes):
            chunk_storage.save_chunk(job.job_id, index, audio_bytes)
            job_manager.mark_chunk_done(job.job_id, index)
            job_manager.increment_progress(job.job_id)

        def check_cancelled() -> bool:
            return job_manager.get_job(job.job_id).state == JobState.CANCELLED

        # Parametri comuni + specifici per xAI
        batch_kwargs = {
            "chunks": chunks,
            "voice_id": voice_id,
            "on_chunk_done": on_chunk_done,
            "check_cancelled": check_cancelled,
        }
        if prompt_data:
            batch_kwargs["prompt_data"] = prompt_data
        if provider == "xai":
            output_format = OutputFormatCatalog.get(output_format_id)
            batch_kwargs["language"] = language
            batch_kwargs["output_format"] = {
                "codec": output_format["codec"],
                "sample_rate": output_format["sample_rate"],
                "bit_rate": output_format["bit_rate"],
            }
            
        if preview_only:
            batch_kwargs["chunks"] = chunks[:1]

        await tts_client.synthesize_batch(**batch_kwargs)

        if job_manager.get_job(job.job_id).state == JobState.CANCELLED:
            logger.info("Job %s cancellato. Merge saltato.", job.job_id)
            return

        if preview_only:
            job_manager.update_state(job.job_id, JobState.REVIEW)
        else:
            # FASE 3: Merge audio da disco
            await _merge_and_complete(job)

    except credit_error_cls as exc:
        wait_seconds = getattr(exc, "retry_after", None)
        if wait_seconds is not None:
            from datetime import datetime, timedelta
            resume_time = datetime.now() + timedelta(seconds=wait_seconds)
            job_manager.set_waiting_quota(
                job.job_id,
                resume_time,
                "Quota giornaliera esaurita. Ripresa automatica in attesa."
            )
        else:
            job_manager.set_paused(
                job.job_id,
                "Credito/quota API esaurito. Ricarica e premi 'Riprendi' per continuare."
            )
    except tts_error_cls as exc:
        job_manager.set_error(
            job.job_id,
            f"Errore API TTS: {exc.message}",
        )
    except Exception as exc:
        logger.exception(
            "Job %s fallito con errore inatteso", job.job_id,
        )
        job_manager.set_error(job.job_id, str(exc))


async def _run_resume_pipeline(job: Job):
    """Pipeline di ripresa: genera solo chunk mancanti → merge."""
    provider = job.provider
    tts_error_cls, credit_error_cls = get_error_classes(provider)

    try:
        # Identifica chunk mancanti
        completed = chunk_storage.get_completed_indices(job.job_id)
        total = job.chunks_total

        # Sincronizza lo stato con i chunk effettivi su disco
        job.chunks_done = completed
        job.chunks_completed = len(completed)
        job.progress_percent = (
            job.chunks_completed / total * 100 if total > 0 else 0
        )

        missing_count = total - len(completed)
        logger.info(
            "Job %s [%s]: ripresa con %d/%d chunk da generare",
            job.job_id, provider, missing_count, total,
        )

        if missing_count == 0:
            await _merge_and_complete(job)
            return

        # Genera solo i chunk mancanti
        tts_client = create_tts_client(provider)

        def on_chunk_done(index: int, audio_bytes: bytes):
            chunk_storage.save_chunk(job.job_id, index, audio_bytes)
            job_manager.mark_chunk_done(job.job_id, index)
            job_manager.increment_progress(job.job_id)

        def check_cancelled() -> bool:
            return job_manager.get_job(job.job_id).state == JobState.CANCELLED

        batch_kwargs = {
            "chunks": job.text_chunks,
            "voice_id": job.voice_id,
            "on_chunk_done": on_chunk_done,
            "skip_indices": completed,
            "check_cancelled": check_cancelled,
        }
        if job.prompt_data:
            batch_kwargs["prompt_data"] = job.prompt_data
        if provider == "xai":
            output_format = OutputFormatCatalog.get(job.output_format_id)
            batch_kwargs["language"] = job.language
            batch_kwargs["output_format"] = {
                "codec": output_format["codec"],
                "sample_rate": output_format["sample_rate"],
                "bit_rate": output_format["bit_rate"],
            }

        await tts_client.synthesize_batch(**batch_kwargs)

        if job_manager.get_job(job.job_id).state == JobState.CANCELLED:
            logger.info("Job %s cancellato (ripresa). Merge saltato.", job.job_id)
            return

        # Merge finale
        await _merge_and_complete(job)

    except credit_error_cls as exc:
        wait_seconds = getattr(exc, "retry_after", None)
        if wait_seconds is not None:
            from datetime import datetime, timedelta
            resume_time = datetime.now() + timedelta(seconds=wait_seconds)
            job_manager.set_waiting_quota(
                job.job_id,
                resume_time,
                "Quota giornaliera esaurita. Ripresa automatica in attesa."
            )
        else:
            job_manager.set_paused(
                job.job_id,
                "Credito/quota API ancora insufficiente. Ricarica e riprova."
            )
    except tts_error_cls as exc:
        job_manager.set_error(
            job.job_id,
            f"Errore API TTS: {exc.message}",
        )
    except Exception as exc:
        logger.exception(
            "Job %s ripresa fallita con errore inatteso", job.job_id,
        )
        job_manager.set_error(job.job_id, str(exc))


async def _merge_and_complete(job: Job):
    """Carica chunk da disco, unisce, e segna il job come completato."""
    job_manager.update_state(job.job_id, JobState.MERGING)
    output_path = AppConfig.OUTPUT_DIR / f"{job.job_id}.mp3"

    audio_chunks = chunk_storage.load_all_chunks(
        job.job_id, job.chunks_total,
    )
    audio_merger.merge_from_bytes(audio_chunks, output_path)

    # Pulizia chunk temporanei
    chunk_storage.cleanup_job(job.job_id)

    # Completato
    job_manager.set_completed(job.job_id, output_path)

import asyncio
from datetime import datetime

async def _quota_watcher_loop():
    """Background task che controlla se ci sono job in attesa di quota e li riavvia."""
    while True:
        try:
            now = datetime.now()
            jobs = job_manager.list_jobs()
            for job_data in jobs:
                if job_data["state"] == JobState.WAITING_QUOTA.value and job_data.get("resume_at"):
                    resume_time = datetime.fromisoformat(job_data["resume_at"])
                    if now >= resume_time:
                        job_id = job_data["job_id"]
                        logger.info("La quota per il job %s dovrebbe essere rinnovata. Ripresa automatica in corso...", job_id)
                        if job_manager.try_set_generating(job_id):
                            job = job_manager.get_job(job_id)
                            if job:
                                asyncio.create_task(_run_resume_pipeline(job))
        except Exception as e:
            logger.error("Errore nel quota_watcher_loop: %s", e)
        
        # Controlla ogni 5 minuti (300 secondi)
        await asyncio.sleep(300)
