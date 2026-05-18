"""
Gestione salvataggio e caricamento chunk audio su disco.
Permette la ripresa delle conversioni interrotte.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from backend.config import AppConfig

logger = logging.getLogger("davetts.chunks")


class ChunkStorage:
    """Salva e recupera chunk audio individuali su disco."""

    CHUNK_PATTERN = "chunk_{index:04d}.mp3"

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or AppConfig.CHUNKS_DIR

    def get_job_dir(self, job_id: str) -> Path:
        """Restituisce la directory dei chunk per un job."""
        return self.base_dir / job_id

    def get_chunk_path(self, job_id: str, index: int) -> Path:
        """Restituisce il percorso previsto per un file chunk."""
        job_dir = self.get_job_dir(job_id)
        return job_dir / self.CHUNK_PATTERN.format(index=index)

    def save_chunk(self, job_id: str, index: int, audio_bytes: bytes) -> Path:
        """
        Salva un singolo chunk audio su disco.
        Ritorna il percorso del file salvato.
        """
        job_dir = self.get_job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        chunk_path = job_dir / self.CHUNK_PATTERN.format(index=index)
        chunk_path.write_bytes(audio_bytes)

        logger.debug(
            "Chunk %d salvato su disco: %s (%.1f KB)",
            index, chunk_path.name,
            len(audio_bytes) / 1024,
        )
        return chunk_path

    def get_completed_indices(self, job_id: str) -> set[int]:
        """
        Restituisce gli indici dei chunk già completati su disco.
        Verifica che i file non siano vuoti (corrotti).
        """
        job_dir = self.get_job_dir(job_id)
        if not job_dir.exists():
            return set()

        completed = set()
        for chunk_file in job_dir.glob("chunk_*.mp3"):
            if chunk_file.stat().st_size > 0:
                index_str = chunk_file.stem.split("_")[1]
                try:
                    completed.add(int(index_str))
                except ValueError:
                    logger.warning(
                        "File chunk con nome non valido: %s",
                        chunk_file.name,
                    )

        return completed

    def load_all_chunks(self, job_id: str, total: int) -> list[bytes]:
        """
        Carica tutti i chunk da disco in ordine.
        Solleva ValueError se mancano chunk.
        """
        job_dir = self.get_job_dir(job_id)
        chunks: list[bytes] = []

        for index in range(total):
            chunk_path = job_dir / self.CHUNK_PATTERN.format(index=index)
            if not chunk_path.exists():
                raise ValueError(
                    f"Chunk {index} mancante per job {job_id}"
                )
            chunks.append(chunk_path.read_bytes())

        logger.info(
            "Caricati %d chunk da disco per job %s",
            total, job_id,
        )
        return chunks

    def cleanup_job(self, job_id: str):
        """Rimuove tutti i chunk di un job dal disco."""
        job_dir = self.get_job_dir(job_id)
        if job_dir.exists():
            shutil.rmtree(job_dir)
            logger.info("Chunk rimossi per job %s", job_id)

    def get_disk_usage(self, job_id: str) -> int:
        """Ritorna lo spazio disco usato dai chunk (in bytes)."""
        job_dir = self.get_job_dir(job_id)
        if not job_dir.exists():
            return 0

        return sum(
            f.stat().st_size
            for f in job_dir.iterdir()
            if f.is_file()
        )
