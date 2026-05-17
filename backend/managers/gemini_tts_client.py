"""
Client per l'API Text-to-Speech di Google Gemini.
Usa l'SDK google-genai per generare audio PCM e lo converte in MP3.
"""

from __future__ import annotations

import asyncio
import logging
import wave
from io import BytesIO
from typing import Callable, Optional

from google import genai
from google.genai import types
from pydub import AudioSegment

from backend.config import AppConfig

logger = logging.getLogger("davetts.gemini_tts")


class GeminiTtsError(Exception):
    """Errore specifico dell'API Gemini TTS."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Gemini TTS Error: {message}")


class GeminiCreditExhaustedError(GeminiTtsError):
    """Il credito/quota Gemini è esaurito."""
    pass


class GeminiTtsClient:
    """Client per l'API Google Gemini TTS con retry automatico."""

    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2.0
    PCM_SAMPLE_RATE = 24000
    PCM_CHANNELS = 1
    PCM_SAMPLE_WIDTH = 2  # 16-bit

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or AppConfig.GEMINI_API_KEY
        self.model = AppConfig.GEMINI_TTS_MODEL
        self._client = None

    def _get_client(self) -> genai.Client:
        """Inizializza il client alla prima richiesta (lazy)."""
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def synthesize(
        self,
        text: str,
        voice_id: str = "Kore",
        **kwargs,
    ) -> bytes:
        """
        Sintetizza un singolo chunk di testo in audio MP3.
        L'API Gemini ritorna PCM raw, che viene convertito in MP3.
        """
        return await self._request_with_retry(text, voice_id)

    async def synthesize_batch(
        self,
        chunks: list[str],
        voice_id: str = "Kore",
        max_concurrent: Optional[int] = None,
        on_chunk_done: Optional[Callable] = None,
        skip_indices: Optional[set[int]] = None,
        **kwargs,
    ) -> list[Optional[bytes]]:
        """
        Sintetizza più chunk in parallelo con concorrenza limitata.
        Interfaccia compatibile con XaiTtsClient.
        """
        concurrency = max_concurrent or AppConfig.MAX_CONCURRENT_REQUESTS
        semaphore = asyncio.Semaphore(concurrency)
        results: list[Optional[bytes]] = [None] * len(chunks)
        skip = skip_indices or set()
        credit_error: Optional[GeminiCreditExhaustedError] = None

        async def _process_chunk(index: int, text: str):
            nonlocal credit_error

            if index in skip:
                logger.info(
                    "Chunk %d/%d saltato (già completato)",
                    index + 1, len(chunks),
                )
                return

            if credit_error is not None:
                return

            async with semaphore:
                logger.info(
                    "Gemini TTS chunk %d/%d (%d caratteri)",
                    index + 1, len(chunks), len(text),
                )
                try:
                    audio_bytes = await self.synthesize(text, voice_id)
                    results[index] = audio_bytes

                    if on_chunk_done:
                        on_chunk_done(index, audio_bytes)

                except GeminiCreditExhaustedError as exc:
                    credit_error = exc
                    logger.warning(
                        "Quota Gemini esaurita al chunk %d/%d",
                        index + 1, len(chunks),
                    )

        tasks = [
            _process_chunk(i, chunk)
            for i, chunk in enumerate(chunks)
        ]
        await asyncio.gather(*tasks)

        if credit_error is not None:
            raise credit_error

        return results

    async def _request_with_retry(
        self, text: str, voice_id: str,
    ) -> bytes:
        """Esegue la richiesta Gemini con retry su errori transitori."""
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                pcm_data = await self._call_gemini_api(text, voice_id)
                mp3_bytes = self._pcm_to_mp3(pcm_data)
                return mp3_bytes

            except GeminiCreditExhaustedError:
                raise

            except Exception as exc:
                last_error = exc
                wait_time = self.RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Errore Gemini TTS (tentativo %d/%d): %s. "
                    "Retry in %.1fs",
                    attempt + 1, self.MAX_RETRIES,
                    str(exc), wait_time,
                )
                await asyncio.sleep(wait_time)

        raise GeminiTtsError(
            f"Tutti i {self.MAX_RETRIES} tentativi falliti: {last_error}"
        )

    async def _call_gemini_api(
        self, text: str, voice_id: str,
    ) -> bytes:
        """Chiama l'API Gemini TTS e ritorna i dati PCM."""
        try:
            response = await asyncio.to_thread(
                self._sync_generate, text, voice_id,
            )

            part = response.candidates[0].content.parts[0]
            return part.inline_data.data

        except Exception as exc:
            error_msg = str(exc).lower()
            if "quota" in error_msg or "429" in error_msg:
                raise GeminiCreditExhaustedError(str(exc))
            raise

    def _sync_generate(self, text: str, voice_id: str):
        """Chiamata sincrona all'API Gemini (usata via to_thread)."""
        return self._get_client().models.generate_content(
            model=self.model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_id,
                        )
                    ),
                ),
            ),
        )

    def _pcm_to_mp3(self, pcm_data: bytes) -> bytes:
        """Converte dati PCM raw (16-bit, 24kHz, mono) in MP3."""
        wav_buffer = BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.PCM_CHANNELS)
            wf.setsampwidth(self.PCM_SAMPLE_WIDTH)
            wf.setframerate(self.PCM_SAMPLE_RATE)
            wf.writeframes(pcm_data)

        wav_buffer.seek(0)
        audio_segment = AudioSegment.from_wav(wav_buffer)

        mp3_buffer = BytesIO()
        audio_segment.export(mp3_buffer, format="mp3", bitrate="128k")
        return mp3_buffer.getvalue()
