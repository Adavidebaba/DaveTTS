"""
Unisce chunk audio MP3 in un singolo file audiobook.
Usa pydub per la concatenazione con pause tra i chunk.
"""

import logging
from io import BytesIO
from pathlib import Path

from pydub import AudioSegment

logger = logging.getLogger("davetts.merger")


class AudioMerger:
    """Concatena file MP3 in un unico audiolibro con pause configurabili."""

    def __init__(self, pause_between_chunks_ms: int = 500):
        self.pause_ms = pause_between_chunks_ms

    def merge_from_bytes(
        self,
        audio_chunks: list[bytes],
        output_path: Path,
    ) -> Path:
        """
        Unisce una lista di bytes audio MP3 in un file finale.
        Inserisce una pausa di silenzio tra ogni chunk.
        """
        if not audio_chunks:
            raise ValueError("Nessun chunk audio da unire")

        logger.info(
            "Inizio merge di %d chunk (pausa: %dms)",
            len(audio_chunks), self.pause_ms,
        )

        silence = AudioSegment.silent(duration=self.pause_ms)
        combined = AudioSegment.empty()

        for index, chunk_bytes in enumerate(audio_chunks):
            segment = AudioSegment.from_mp3(BytesIO(chunk_bytes))

            if index > 0:
                combined += silence

            combined += segment

            logger.debug(
                "Chunk %d/%d aggiunto (%.1fs)",
                index + 1, len(audio_chunks),
                len(segment) / 1000.0,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined.export(str(output_path), format="mp3")

        duration_seconds = len(combined) / 1000.0
        file_size_mb = output_path.stat().st_size / (1024 * 1024)

        logger.info(
            "Merge completato: %.1f minuti, %.1f MB -> %s",
            duration_seconds / 60, file_size_mb, output_path.name,
        )

        return output_path

    def merge_from_files(
        self,
        chunk_paths: list[Path],
        output_path: Path,
    ) -> Path:
        """
        Unisce file MP3 da disco in un file finale.
        Alternativa a merge_from_bytes per chunk molto grandi.
        """
        audio_chunks = []
        for path in chunk_paths:
            audio_chunks.append(path.read_bytes())

        return self.merge_from_bytes(audio_chunks, output_path)
