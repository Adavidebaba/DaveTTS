"""
Gestione dei job di generazione audiolibro.
Traccia stato, progresso e risultati in memoria con persistenza su disco.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from backend.models.schemas import JobState
from backend.managers.job_persistence import JobPersistence

logger = logging.getLogger("davetts.jobs")


class Job:
    """Rappresenta un singolo job di generazione."""

    def __init__(self, file_name: str, file_path: Path, job_id: str | None = None):
        self.job_id: str = job_id or uuid.uuid4().hex[:12]
        self.file_name: str = file_name
        self.file_path: Path = file_path
        self.state: JobState = JobState.PENDING
        self.progress_percent: float = 0.0
        self.chunks_total: int = 0
        self.chunks_completed: int = 0
        self.error_message: str | None = None
        self.output_path: Path | None = None
        self.created_at: datetime = datetime.now()
        self.audio_chunks: list[bytes] = []

        # Campi per la ripresa
        self.chunks_done: set[int] = set()
        self.voice_id: str = ""
        self.language: str = ""
        self.output_format_id: str = ""
        self.text_chunks: list[str] = []
        self.provider: str = "gemini"
        self.prompt_data: dict | None = None
        self.resume_at: datetime | None = None

    @property
    def is_resumable(self) -> bool:
        """Un job è riprendibile se è paused/error con chunk parziali o se in WAITING_QUOTA."""
        if self.state not in (JobState.PAUSED, JobState.ERROR, JobState.CANCELLED, JobState.WAITING_QUOTA):
            return False
        return (
            len(self.chunks_done) > 0
            and len(self.chunks_done) < self.chunks_total
        )

    def to_dict(self) -> dict:
        """Serializza il job per la risposta API."""
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "file_name": self.file_name,
            "progress_percent": round(self.progress_percent, 1),
            "chunks_total": self.chunks_total,
            "chunks_completed": self.chunks_completed,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "is_resumable": self.is_resumable,
            "resume_at": self.resume_at.isoformat() if self.resume_at else None,
        }


class JobManager:
    """Gestisce il ciclo di vita dei job con persistenza su disco."""

    CLEANUP_AFTER_HOURS = 24

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._persistence = JobPersistence()
        self._restore_persisted_jobs()

    def _restore_persisted_jobs(self):
        """Carica job paused/error dal disco all'avvio."""
        persisted = self._persistence.load_all_paused_jobs()
        for data in persisted:
            fields = JobPersistence.deserialize_to_fields(data)
            job = Job(
                file_name=fields["file_name"],
                file_path=Path(fields["file_path"]),
            )
            job.job_id = fields["job_id"]
            job.state = JobState(fields["state"])
            job.progress_percent = fields["progress_percent"]
            job.chunks_total = fields["chunks_total"]
            job.chunks_completed = fields["chunks_completed"]
            job.error_message = fields["error_message"]
            job.chunks_done = fields["chunks_done"]
            job.voice_id = fields["voice_id"]
            job.language = fields["language"]
            job.output_format_id = fields["output_format_id"]
            job.text_chunks = fields["text_chunks"]
            job.provider = fields["provider"]
            job.prompt_data = fields.get("prompt_data")

            if fields["created_at"]:
                try:
                    job.created_at = datetime.fromisoformat(fields["created_at"])
                except ValueError:
                    pass

            if fields.get("resume_at"):
                try:
                    job.resume_at = datetime.fromisoformat(fields["resume_at"])
                except ValueError:
                    pass

            self._jobs[job.job_id] = job
            logger.info(
                "Job %s ripristinato (stato: %s, %d/%d chunk)",
                job.job_id, job.state.value,
                job.chunks_completed, job.chunks_total,
            )

    def _persist_job(self, job: Job):
        """Salva lo stato del job su disco se paused/error/cancelled/waiting_quota."""
        if job.state in (JobState.PAUSED, JobState.ERROR, JobState.CANCELLED, JobState.WAITING_QUOTA):
            data = JobPersistence.serialize_job(job)
            self._persistence.save_job_state(data)
        elif job.state == JobState.COMPLETED:
            self._persistence.delete_job_state(job.job_id)

    def create_job(self, file_name: str, file_path: Path, job_id: str | None = None) -> Job:
        """Crea un nuovo job e lo registra."""
        job = Job(file_name, file_path, job_id)

        with self._lock:
            self._cleanup_old_jobs()
            self._jobs[job.job_id] = job

        logger.info("Job creato: %s per '%s'", job.job_id, file_name)
        return job

    def get_job(self, job_id: str) -> Job | None:
        """Recupera un job per ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def update_state(self, job_id: str, state: JobState):
        """Aggiorna lo stato di un job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.state = state
                logger.info("Job %s -> %s", job_id, state.value)

    def try_set_generating(self, job_id: str) -> bool:
        """Imposta il job in stato GENERATING in modo atomico, prevenendo race conditions. Ritorna True se è stato possibile avviare la generazione."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            # Se è già in corso o completato, non avviamo un nuovo task
            if job.state in (JobState.PENDING, JobState.SPLITTING, JobState.GENERATING, JobState.MERGING, JobState.COMPLETED):
                return False
            
            job.state = JobState.GENERATING
            job.error_message = None
            logger.info("Job %s -> %s (atomic start)", job_id, JobState.GENERATING.value)
            return True

    def set_chunks_total(self, job_id: str, total: int):
        """Imposta il numero totale di chunk."""
        job = self.get_job(job_id)
        if job:
            job.chunks_total = total

    def increment_progress(self, job_id: str):
        """Incrementa il contatore chunk completati e ricalcola %."""
        job = self.get_job(job_id)
        if job and job.chunks_total > 0:
            job.chunks_completed += 1
            job.progress_percent = (
                job.chunks_completed / job.chunks_total * 100
            )

    def set_error(self, job_id: str, message: str):
        """Segna il job come fallito."""
        job = self.get_job(job_id)
        if job:
            job.state = JobState.ERROR
            job.error_message = message
            self._persist_job(job)
            logger.error("Job %s fallito: %s", job_id, message)

    def set_completed(self, job_id: str, output_path: Path):
        """Segna il job come completato."""
        job = self.get_job(job_id)
        if job:
            job.state = JobState.COMPLETED
            job.output_path = output_path
            job.progress_percent = 100.0
            self._persist_job(job)
            logger.info("Job %s completato: %s", job_id, output_path)

    def set_paused(self, job_id: str, message: str):
        """Segna il job come in pausa (riprendibile)."""
        job = self.get_job(job_id)
        if job:
            job.state = JobState.PAUSED
            job.error_message = message
            self._persist_job(job)
            logger.warning("Job %s in pausa: %s", job_id, message)

    def set_cancelled(self, job_id: str, message: str):
        """Segna il job come interrotto dall'utente."""
        job = self.get_job(job_id)
        if job:
            job.state = JobState.CANCELLED
            job.error_message = message
            job.resume_at = None
            self._persist_job(job)
            logger.info("Job %s cancellato: %s", job_id, message)

    def set_waiting_quota(self, job_id: str, resume_at: datetime, message: str):
        """Segna il job in attesa del rinnovo quota."""
        job = self.get_job(job_id)
        if job:
            job.state = JobState.WAITING_QUOTA
            job.error_message = message
            job.resume_at = resume_at
            self._persist_job(job)
            logger.warning("Job %s in attesa quota fino a %s: %s", job_id, resume_at.isoformat(), message)

    def set_generation_params(
        self,
        job_id: str,
        voice_id: str,
        language: str,
        output_format_id: str,
        text_chunks: list[str],
        provider: str = "gemini",
        prompt_data: dict | None = None,
    ):
        """Salva i parametri di generazione per la ripresa."""
        job = self.get_job(job_id)
        if job:
            job.voice_id = voice_id
            job.language = language
            job.output_format_id = output_format_id
            job.text_chunks = text_chunks
            job.provider = provider
            job.prompt_data = prompt_data

    def mark_chunk_done(self, job_id: str, chunk_index: int):
        """Registra un chunk come completato."""
        job = self.get_job(job_id)
        if job:
            job.chunks_done.add(chunk_index)

    def list_jobs(self) -> list[dict]:
        """Lista tutti i job attivi (non scaduti)."""
        with self._lock:
            self._cleanup_old_jobs()
            return [
                job.to_dict()
                for job in sorted(
                    self._jobs.values(),
                    key=lambda j: j.created_at,
                    reverse=True,
                )
            ]

    def _cleanup_old_jobs(self):
        """Rimuove job completati più vecchi di CLEANUP_AFTER_HOURS."""
        cutoff = datetime.now() - timedelta(hours=self.CLEANUP_AFTER_HOURS)
        expired = [
            jid for jid, job in self._jobs.items()
            if job.state in (
                JobState.COMPLETED, JobState.ERROR, JobState.PAUSED, JobState.CANCELLED, JobState.WAITING_QUOTA
            )
            and job.created_at < cutoff
        ]
        for jid in expired:
            del self._jobs[jid]
            logger.debug("Job %s rimosso (scaduto)", jid)
