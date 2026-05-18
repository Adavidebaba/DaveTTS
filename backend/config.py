"""
Configurazione centralizzata per DaveTTS.
Legge le variabili d'ambiente e definisce costanti globali.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Provider TTS supportati
SUPPORTED_PROVIDERS = ("xai", "gemini")


class OutputFormatCatalog:
    """Formati audio supportati dall'API xAI TTS."""

    FORMATS = {
        "standard": {
            "codec": "mp3",
            "sample_rate": 44100,
            "bit_rate": 128000,
            "label": "MP3 Standard (44.1 kHz, 128 kbps)",
        },
        "high": {
            "codec": "mp3",
            "sample_rate": 44100,
            "bit_rate": 192000,
            "label": "MP3 Alta Qualità (44.1 kHz, 192 kbps)",
        },
        "low": {
            "codec": "mp3",
            "sample_rate": 24000,
            "bit_rate": 128000,
            "label": "MP3 Leggero (24 kHz, 128 kbps)",
        },
    }

    @classmethod
    def get(cls, format_id: str) -> dict:
        return cls.FORMATS.get(format_id, cls.FORMATS["standard"])

    @classmethod
    def get_all(cls) -> dict:
        return cls.FORMATS


class AppConfig:
    """Configurazione principale dell'applicazione."""

    # Provider TTS attivo (default: gemini)
    TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "gemini")

    # API xAI
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    XAI_TTS_URL: str = "https://api.x.ai/v1/tts"

    # API Google Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_TTS_MODEL: str = "gemini-3.1-flash-tts-preview"

    # Costi per 1M caratteri in USD
    PRICE_PER_1M_CHARS_XAI: float = 15.00
    PRICE_PER_1M_CHARS_GEMINI: float = 20.00  # Free tier Gemini

    # Limiti testo
    MAX_CHUNK_SIZE: int = 1_000  # Limite ridotto a 1k caratteri per Gemini (limite 4096 output tokens)
    MAX_UPLOAD_SIZE_MB: int = 10

    # Parallelismo API
    MAX_CONCURRENT_REQUESTS: int = int(
        os.getenv("MAX_CONCURRENT_REQUESTS", "20")
    )

    # Audio merge
    PAUSE_BETWEEN_CHUNKS_MS: int = 500

    # Percorsi dati
    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    UPLOADS_DIR: Path = DATA_DIR / "uploads"
    OUTPUT_DIR: Path = DATA_DIR / "output"
    TEMP_DIR: Path = DATA_DIR / "temp"
    CHUNKS_DIR: Path = DATA_DIR / "chunks"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 4300

    @classmethod
    def get_price_per_1m_chars(cls, provider: str | None = None) -> float:
        """Ritorna il costo per 1M caratteri del provider specificato."""
        prov = provider or cls.TTS_PROVIDER
        if prov == "gemini":
            return cls.PRICE_PER_1M_CHARS_GEMINI
        return cls.PRICE_PER_1M_CHARS_XAI

    @classmethod
    def ensure_directories(cls):
        """Crea le directory necessarie se non esistono."""
        cls.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        cls.CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls, provider: str | None = None) -> list[str]:
        """Valida la configurazione per il provider specificato."""
        prov = provider or cls.TTS_PROVIDER
        errors = []

        if prov not in SUPPORTED_PROVIDERS:
            errors.append(
                f"TTS_PROVIDER '{prov}' non valido. "
                f"Usa: {SUPPORTED_PROVIDERS}"
            )
            return errors

        if prov == "xai":
            if not cls.XAI_API_KEY:
                errors.append("XAI_API_KEY non configurata")
            elif not cls.XAI_API_KEY.startswith("xai-"):
                errors.append("XAI_API_KEY deve iniziare con 'xai-'")

        elif prov == "gemini":
            if not cls.GEMINI_API_KEY:
                errors.append("GEMINI_API_KEY non configurata")

        return errors
