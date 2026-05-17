"""
Persistenza dello stato dei job su disco.
Salva e carica lo stato in JSON per sopravvivere ai riavvii del container.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from backend.config import AppConfig

logger = logging.getLogger("davetts.persistence")


class JobPersistence:
    """Salva e carica lo stato dei job su disco come JSON."""

    STATE_FILE = "job_state.json"

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or AppConfig.CHUNKS_DIR

    def save_job_state(self, job_data: dict):
        """Salva lo stato di un job su disco."""
        job_id = job_data["job_id"]
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        state_path = job_dir / self.STATE_FILE
        state_path.write_text(
            json.dumps(job_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.debug("Stato job %s salvato su disco", job_id)

    def load_all_paused_jobs(self) -> list[dict]:
        """
        Carica tutti i job in stato paused/error dal disco.
        Usato all'avvio per ripopolare il JobManager.
        """
        if not self.base_dir.exists():
            return []

        jobs = []
        for job_dir in self.base_dir.iterdir():
            if not job_dir.is_dir():
                continue

            state_path = job_dir / self.STATE_FILE
            if not state_path.exists():
                continue

            try:
                job_data = json.loads(
                    state_path.read_text(encoding="utf-8"),
                )
                if job_data.get("state") in ("paused", "error"):
                    jobs.append(job_data)
                    logger.info(
                        "Job %s caricato da disco (stato: %s)",
                        job_data["job_id"],
                        job_data["state"],
                    )
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning(
                    "Impossibile caricare job da %s: %s",
                    state_path, exc,
                )

        return jobs

    def delete_job_state(self, job_id: str):
        """Rimuove il file di stato di un job."""
        state_path = self.base_dir / job_id / self.STATE_FILE
        if state_path.exists():
            state_path.unlink()
            logger.debug("Stato job %s rimosso", job_id)

    @staticmethod
    def serialize_job(job) -> dict:
        """Converte un oggetto Job in dizionario serializzabile."""
        return {
            "job_id": job.job_id,
            "file_name": job.file_name,
            "file_path": str(job.file_path),
            "state": job.state.value,
            "progress_percent": job.progress_percent,
            "chunks_total": job.chunks_total,
            "chunks_completed": job.chunks_completed,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat(),
            "chunks_done": list(job.chunks_done),
            "voice_id": job.voice_id,
            "language": job.language,
            "output_format_id": job.output_format_id,
            "text_chunks": job.text_chunks,
        }

    @staticmethod
    def deserialize_to_fields(data: dict) -> dict:
        """
        Converte un dizionario JSON nei campi necessari
        per ricostruire un Job.
        """
        return {
            "job_id": data["job_id"],
            "file_name": data["file_name"],
            "file_path": data["file_path"],
            "state": data["state"],
            "progress_percent": data.get("progress_percent", 0.0),
            "chunks_total": data.get("chunks_total", 0),
            "chunks_completed": data.get("chunks_completed", 0),
            "error_message": data.get("error_message"),
            "created_at": data.get("created_at"),
            "chunks_done": set(data.get("chunks_done", [])),
            "voice_id": data.get("voice_id", ""),
            "language": data.get("language", ""),
            "output_format_id": data.get("output_format_id", ""),
            "text_chunks": data.get("text_chunks", []),
        }
