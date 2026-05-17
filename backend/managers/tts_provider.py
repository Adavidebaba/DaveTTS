"""
Factory per selezionare il client TTS corretto in base al provider.
Fornisce un'interfaccia unificata per xAI e Gemini.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.config import AppConfig

logger = logging.getLogger("davetts.provider")


def create_tts_client(provider: Optional[str] = None):
    """
    Crea e ritorna il client TTS appropriato per il provider.
    Ritorna XaiTtsClient o GeminiTtsClient con la stessa interfaccia.
    """
    active_provider = provider or AppConfig.TTS_PROVIDER

    if active_provider == "xai":
        from backend.managers.tts_client import XaiTtsClient
        logger.info("Provider TTS selezionato: xAI")
        return XaiTtsClient()

    if active_provider == "gemini":
        from backend.managers.gemini_tts_client import GeminiTtsClient
        logger.info("Provider TTS selezionato: Google Gemini")
        return GeminiTtsClient()

    raise ValueError(f"Provider TTS sconosciuto: {active_provider}")


def get_error_classes(provider: Optional[str] = None):
    """
    Ritorna le classi di errore appropriate per il provider.
    Tupla: (GenericError, CreditExhaustedError)
    """
    active_provider = provider or AppConfig.TTS_PROVIDER

    if active_provider == "xai":
        from backend.managers.tts_client import (
            TtsApiError, CreditExhaustedError,
        )
        return TtsApiError, CreditExhaustedError

    if active_provider == "gemini":
        from backend.managers.gemini_tts_client import (
            GeminiTtsError, GeminiCreditExhaustedError,
        )
        return GeminiTtsError, GeminiCreditExhaustedError

    raise ValueError(f"Provider TTS sconosciuto: {active_provider}")
