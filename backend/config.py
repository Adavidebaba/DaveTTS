"""
Configurazione centralizzata per DaveTTS.
Legge le variabili d'ambiente e definisce costanti globali.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class VoiceCatalog:
    """Catalogo voci disponibili dall'API xAI TTS."""

    VOICES = {
        "leo": {
            "name": "Leo",
            "description": "Autorevole e forte",
            "icon": "🦁",
        },
        "eve": {
            "name": "Eve",
            "description": "Energica e vivace",
            "icon": "✨",
        },
        "ara": {
            "name": "Ara",
            "description": "Calda e amichevole",
            "icon": "🌸",
        },
        "rex": {
            "name": "Rex",
            "description": "Sicuro e chiaro",
            "icon": "👑",
        },
        "sal": {
            "name": "Sal",
            "description": "Morbido e bilanciato",
            "icon": "🎵",
        },
    }

    @classmethod
    def is_valid(cls, voice_id: str) -> bool:
        return voice_id.lower() in cls.VOICES

    @classmethod
    def get_all(cls) -> dict:
        return cls.VOICES


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

    # API xAI
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    XAI_TTS_URL: str = "https://api.x.ai/v1/tts"
    PRICE_PER_1M_CHARS: float = 15.00  # Costo per 1 milione di caratteri in USD

    # Limiti testo
    MAX_CHUNK_SIZE: int = 10_000  # Margine sicurezza vs limite API 15.000
    MAX_UPLOAD_SIZE_MB: int = 10

    # Parallelismo API (limite xAI: 100 sessioni, 50 RPS)
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
    def ensure_directories(cls):
        """Crea le directory necessarie se non esistono."""
        cls.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        cls.CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls) -> list[str]:
        """Valida la configurazione. Ritorna lista errori."""
        errors = []
        if not cls.XAI_API_KEY:
            errors.append("XAI_API_KEY non configurata")
        elif not cls.XAI_API_KEY.startswith("xai-"):
            errors.append("XAI_API_KEY deve iniziare con 'xai-'")
        return errors
