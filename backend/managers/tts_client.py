"""
Client per l'API Text-to-Speech di xAI.
Gestisce chiamate singole e batch con retry e backoff esponenziale.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional
from pathlib import Path

import httpx

from backend.config import AppConfig

logger = logging.getLogger("davetts.tts")

# Codici HTTP che indicano credito esaurito
CREDIT_EXHAUSTED_CODES = {402, 403}


class TtsApiError(Exception):
    """Errore specifico dell'API TTS."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"TTS API Error {status_code}: {message}")


class CreditExhaustedError(TtsApiError):
    """Il credito API è esaurito."""

    def __init__(self, status_code: int, message: str):
        super().__init__(status_code, message)


class XaiTtsClient:
    """Client asincrono per l'API xAI TTS con retry automatico."""

    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2.0  # secondi
    REQUEST_TIMEOUT = 120.0  # secondi per chunk

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or AppConfig.XAI_API_KEY
        self.api_url = AppConfig.XAI_TTS_URL

    async def synthesize(
        self,
        text: str,
        voice_id: str = "leo",
        language: str = "it",
        output_format: Optional[dict] = None,
    ) -> bytes:
        """
        Sintetizza un singolo chunk di testo in audio.
        Ritorna i bytes audio grezzi (MP3).
        """
        if output_format is None:
            output_format = {
                "codec": "mp3",
                "sample_rate": 44100,
                "bit_rate": 128000,
            }

        payload = {
            "text": text,
            "voice_id": voice_id,
            "output_format": output_format,
            "language": language,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        return await self._request_with_retry(headers, payload)

    async def synthesize_batch(
        self,
        chunks: list[str],
        voice_id: str = "leo",
        language: str = "it",
        output_format: Optional[dict] = None,
        max_concurrent: Optional[int] = None,
        on_chunk_done: Optional[Callable] = None,
        skip_indices: Optional[set[int]] = None,
        check_cancelled: Optional[Callable[[], bool]] = None,
    ) -> list[Optional[bytes]]:
        """
        Sintetizza più chunk in parallelo con concorrenza limitata.
        Salta i chunk in skip_indices (già completati).
        Chiama on_chunk_done(index, audio_bytes) dopo ogni chunk.
        Solleva CreditExhaustedError se il credito si esaurisce.
        """
        concurrency = max_concurrent or AppConfig.MAX_CONCURRENT_REQUESTS
        semaphore = asyncio.Semaphore(concurrency)
        results: list[Optional[bytes]] = [None] * len(chunks)
        skip = skip_indices or set()
        credit_error: Optional[CreditExhaustedError] = None

        async def _process_chunk(index: int, text: str):
            nonlocal credit_error

            if index in skip:
                logger.info(
                    "Chunk %d/%d saltato (già completato)",
                    index + 1, len(chunks),
                )
                return

            async with semaphore:
                # Se il credito è esaurito, non tentare altri chunk
                if credit_error is not None:
                    return

                if check_cancelled and check_cancelled():
                    return

                logger.info(
                    "Generazione chunk %d/%d (%d caratteri)",
                    index + 1, len(chunks), len(text),
                )
                try:
                    audio_bytes = await self.synthesize(
                        text, voice_id, language, output_format,
                    )
                    results[index] = audio_bytes

                    if on_chunk_done:
                        on_chunk_done(index, audio_bytes)

                except CreditExhaustedError as exc:
                    credit_error = exc
                    logger.warning(
                        "Credito esaurito al chunk %d/%d",
                        index + 1, len(chunks),
                    )

        tasks = [
            _process_chunk(i, chunk)
            for i, chunk in enumerate(chunks)
        ]
        await asyncio.gather(*tasks)

        # Se il credito si è esaurito, propagare l'errore
        if credit_error is not None:
            raise credit_error

        return results

    async def _request_with_retry(
        self, headers: dict, payload: dict,
    ) -> bytes:
        """Esegue la richiesta con retry su errori transitori."""
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=self.REQUEST_TIMEOUT,
                ) as client:
                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        json=payload,
                    )

                if response.status_code == 200:
                    return response.content

                # Credito esaurito — non recuperabile con retry
                if response.status_code in CREDIT_EXHAUSTED_CODES:
                    error_text = response.text[:500]
                    raise CreditExhaustedError(
                        response.status_code, error_text,
                    )

                if response.status_code == 429:
                    wait_time = self.RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "Rate limited (429). Attendo %.1fs "
                        "prima del retry %d/%d",
                        wait_time, attempt + 1, self.MAX_RETRIES,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code >= 500:
                    wait_time = self.RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "Errore server (%d). Retry %d/%d in %.1fs",
                        response.status_code, attempt + 1,
                        self.MAX_RETRIES, wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Errori 4xx non recuperabili (escluso 429 e credito)
                error_text = response.text[:500]
                raise TtsApiError(response.status_code, error_text)

            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "Timeout richiesta. Retry %d/%d",
                    attempt + 1, self.MAX_RETRIES,
                )
                await asyncio.sleep(self.RETRY_BACKOFF_BASE)
            except httpx.RequestError as exc:
                last_error = exc
                logger.warning(
                    "Errore rete: %s. Retry %d/%d",
                    str(exc), attempt + 1, self.MAX_RETRIES,
                )
                await asyncio.sleep(self.RETRY_BACKOFF_BASE)

        raise TtsApiError(
            0, f"Tutti i {self.MAX_RETRIES} tentativi falliti: {last_error}",
        )
