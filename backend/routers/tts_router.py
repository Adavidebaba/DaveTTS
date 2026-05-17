"""
Router per la generazione TTS degli audiolibri.
Gestisce avvio generazione asincrona in background.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.config import AppConfig, VoiceCatalog, OutputFormatCatalog
from backend.managers.text_splitter import TextSplitter
from backend.managers.tts_client import (
    XaiTtsClient, TtsApiError, CreditExhaustedError,
)
from backend.managers.audio_merger import AudioMerger
from backend.managers.chunk_storage import ChunkStorage
from backend.managers.job_manager import JobManager, Job
from backend.models.schemas import GenerateRequest, JobState

logger = logging.getLogger("davetts.tts_router")
router = APIRouter(prefix="/api", tags=["tts"])

# Istanze condivise (singleton a livello di modulo)
job_manager = JobManager()
text_splitter = TextSplitter(AppConfig.MAX_CHUNK_SIZE)
tts_client = XaiTtsClient()
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
    # Validazione API key
    config_errors = AppConfig.validate()
    if config_errors:
        raise HTTPException(status_code=500, detail=config_errors[0])

    # Validazione voce
    if not VoiceCatalog.is_valid(request.voice_id):
        raise HTTPException(
            status_code=400,
            detail=f"Voce '{request.voice_id}' non valida",
        )

    # Verifica file esiste
    file_path = AppConfig.UPLOADS_DIR / f"{request.file_id}.txt"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File non trovato")

    # Crea job
    job = job_manager.create_job(
        file_name=file_path.stem,
        file_path=file_path,
    )

    # Avvia generazione in background
    background_tasks.add_task(
        _run_generation_pipeline,
        job=job,
        voice_id=request.voice_id,
        language=request.language,
        output_format_id=request.output_format,
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

    if job.state not in (JobState.PAUSED, JobState.ERROR):
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

    # Validazione API key (potrebbe essere cambiata)
    config_errors = AppConfig.validate()
    if config_errors:
        raise HTTPException(status_code=500, detail=config_errors[0])

    # Reset stato per la ripresa
    job.error_message = None
    job_manager.update_state(job_id, JobState.GENERATING)

    background_tasks.add_task(
        _run_resume_pipeline,
        job=job,
    )

    return {
        "job_id": job.job_id,
        "message": "Generazione ripresa",
    }


async def _run_generation_pipeline(
    job: Job,
    voice_id: str,
    language: str,
    output_format_id: str,
):
    """Pipeline completa: split → TTS → merge."""
    try:
        # FASE 1: Split testo
        job_manager.update_state(job.job_id, JobState.SPLITTING)
        text = job.file_path.read_text(encoding="utf-8")
        chunks = text_splitter.split(text)
        job_manager.set_chunks_total(job.job_id, len(chunks))

        # Salva parametri per eventuale ripresa
        job_manager.set_generation_params(
            job.job_id, voice_id, language, output_format_id, chunks,
        )

        logger.info(
            "Job %s: testo diviso in %d chunk",
            job.job_id, len(chunks),
        )

        # FASE 2: Generazione TTS con salvataggio progressivo
        job_manager.update_state(job.job_id, JobState.GENERATING)
        output_format = OutputFormatCatalog.get(output_format_id)
        format_params = {
            "codec": output_format["codec"],
            "sample_rate": output_format["sample_rate"],
            "bit_rate": output_format["bit_rate"],
        }

        def on_chunk_done(index: int, audio_bytes: bytes):
            chunk_storage.save_chunk(job.job_id, index, audio_bytes)
            job_manager.mark_chunk_done(job.job_id, index)
            job_manager.increment_progress(job.job_id)

        await tts_client.synthesize_batch(
            chunks=chunks,
            voice_id=voice_id,
            language=language,
            output_format=format_params,
            on_chunk_done=on_chunk_done,
        )

        # FASE 3: Merge audio da disco
        await _merge_and_complete(job)

    except CreditExhaustedError as exc:
        job_manager.set_paused(
            job.job_id,
            "Credito API esaurito. Ricarica il credito e "
            "premi 'Riprendi' per continuare.",
        )
    except TtsApiError as exc:
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
            "Job %s: ripresa con %d/%d chunk da generare",
            job.job_id, missing_count, total,
        )

        if missing_count == 0:
            # Tutti i chunk ci sono, procedi al merge
            await _merge_and_complete(job)
            return

        # Genera solo i chunk mancanti
        output_format = OutputFormatCatalog.get(job.output_format_id)
        format_params = {
            "codec": output_format["codec"],
            "sample_rate": output_format["sample_rate"],
            "bit_rate": output_format["bit_rate"],
        }

        def on_chunk_done(index: int, audio_bytes: bytes):
            chunk_storage.save_chunk(job.job_id, index, audio_bytes)
            job_manager.mark_chunk_done(job.job_id, index)
            job_manager.increment_progress(job.job_id)

        await tts_client.synthesize_batch(
            chunks=job.text_chunks,
            voice_id=job.voice_id,
            language=job.language,
            output_format=format_params,
            on_chunk_done=on_chunk_done,
            skip_indices=completed,
        )

        # Merge finale
        await _merge_and_complete(job)

    except CreditExhaustedError:
        job_manager.set_paused(
            job.job_id,
            "Credito API ancora insufficiente. "
            "Ricarica e riprova.",
        )
    except TtsApiError as exc:
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
