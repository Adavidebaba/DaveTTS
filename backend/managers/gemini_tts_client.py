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

    MAX_RETRIES = 10
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
        # Per Gemini riduciamo la concorrenza massima per evitare errori 429 (Rate Limit)
        base_concurrency = max_concurrent or AppConfig.MAX_CONCURRENT_REQUESTS
        concurrency = min(base_concurrency, 2) 
        
        semaphore = asyncio.Semaphore(concurrency)
        results: list[Optional[bytes]] = [None] * len(chunks)
        skip = skip_indices or set()
        credit_error: Optional[GeminiCreditExhaustedError] = None
        prompt_data = kwargs.get("prompt_data")

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

            # Costruisci il prompt se presente
            if prompt_data:
                formatted_text = self._format_prompt(text, prompt_data)
            else:
                formatted_text = text

            async with semaphore:
                # Piccolo ritardo per scaglionare le richieste
                await asyncio.sleep(index * 0.5)
                logger.info(
                    "Gemini TTS chunk %d/%d (%d caratteri base)",
                    index + 1, len(chunks), len(text),
                )
                try:
                    audio_bytes = await self.synthesize(formatted_text, voice_id)
                    results[index] = audio_bytes

                    if on_chunk_done:
                        on_chunk_done(index, audio_bytes)

                except GeminiCreditExhaustedError as exc:
                    credit_error = exc
                    logger.warning(
                        "Quota/Rate Limit Gemini esaurito al chunk %d/%d",
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

    def _format_prompt(self, text: str, prompt_data: dict) -> str:
        """Formatta il testo in un prompt avanzato per Gemini TTS."""
        parts = []
        if prompt_data.get("audioProfile"):
            parts.append(prompt_data["audioProfile"])
        if prompt_data.get("scene"):
            parts.append(prompt_data["scene"])
        if prompt_data.get("directorsNotes"):
            parts.append(prompt_data["directorsNotes"])
        if prompt_data.get("sampleContext"):
            parts.append(prompt_data["sampleContext"])
            
        parts.append("#### TRANSCRIPT\n" + text)
        
        return "\n\n".join(parts)

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

            except Exception as exc:
                last_error = exc
                error_str = str(exc)
                
                # Se è un errore di credito/budget permanente, interrompi subito senza retry
                if "spending cap" in error_str.lower():
                    raise GeminiCreditExhaustedError(error_str)
                
                # Cerca un delay specifico richiesto da Google per i rate limit temporanei
                import re
                match = re.search(r'Please retry in ([0-9.]+)s', error_str)
                if match:
                    wait_time = float(match.group(1)) + 2.0  # Aggiungi 2s di margine
                else:
                    wait_time = self.RETRY_BACKOFF_BASE ** (attempt + 1)
                
                logger.warning(
                    "Errore Gemini TTS (tentativo %d/%d): %s. "
                    "Retry in %.1fs",
                    attempt + 1, self.MAX_RETRIES,
                    error_str, wait_time,
                )
                await asyncio.sleep(wait_time)

        if isinstance(last_error, GeminiCreditExhaustedError):
            raise last_error

        raise GeminiTtsError(
            f"Tutti i {self.MAX_RETRIES} tentativi falliti: {last_error}"
        )

    async def _call_gemini_api(
        self, text: str, voice_id: str,
    ) -> bytes:
        """Chiama l'API Gemini TTS e ritorna i dati PCM."""
        try:
            # Aggiungiamo un timeout di 600 secondi (10 minuti) per task lunghi ma evitando blocchi eterni
            response = await asyncio.wait_for(
                asyncio.to_thread(self._sync_generate, text, voice_id),
                timeout=600.0
            )

            if not response.candidates:
                raise GeminiTtsError(f"Risposta vuota da Gemini (forse bloccato dai filtri di sicurezza). Dettagli: {response}")

            content = response.candidates[0].content
            if not content or not content.parts:
                raise GeminiTtsError(f"Contenuto audio mancante nella risposta. Dettagli: {response}")

            part = content.parts[0]
            if not part.inline_data:
                raise GeminiTtsError(f"Nessun dato audio (inline_data) restituito. Dettagli: {response}")

            return part.inline_data.data

        except asyncio.TimeoutError:
            raise GeminiTtsError("La richiesta a Gemini è andata in timeout (600s)")
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
                safety_settings=[
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                ],
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
