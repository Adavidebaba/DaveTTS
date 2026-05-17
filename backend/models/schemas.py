"""
Modelli Pydantic per richieste e risposte API.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class JobState(str, Enum):
    """Stati possibili di un job di generazione."""
    PENDING = "pending"
    SPLITTING = "splitting"
    GENERATING = "generating"
    MERGING = "merging"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"


class OutputFormatRequest(BaseModel):
    """Formato audio richiesto."""
    codec: str = "mp3"
    sample_rate: int = 44100
    bit_rate: int = 128000


class GenerateRequest(BaseModel):
    """Richiesta di generazione audiolibro."""
    file_id: str = Field(..., description="ID del file caricato")
    voice_id: str = Field(default="Kore", description="Voce da usare")
    language: str = Field(default="it", description="Codice lingua BCP-47")
    output_format: str = Field(
        default="standard",
        description="Preset formato: standard, high, low"
    )
    provider: str = Field(
        default="gemini",
        description="Provider TTS: gemini o xai"
    )


class ChunkStatus(BaseModel):
    """Stato di un singolo chunk."""
    index: int
    total_chars: int
    status: str = "pending"


class JobStatusResponse(BaseModel):
    """Risposta con lo stato di un job."""
    job_id: str
    state: JobState
    progress_percent: float = 0.0
    chunks_total: int = 0
    chunks_completed: int = 0
    error_message: str | None = None
    file_name: str = ""
    is_resumable: bool = False


class UploadResponse(BaseModel):
    """Risposta dopo upload di un file."""
    file_id: str
    file_name: str
    text_length: int
    estimated_chunks: int


class ConfigResponse(BaseModel):
    """Risposta con la configurazione corrente."""
    api_key_configured: bool
    voices: dict
    output_formats: dict
    price_per_1m_chars: float
    provider: str = "gemini"
    providers: dict = {}


class JobListItem(BaseModel):
    """Elemento nella lista dei job."""
    job_id: str
    state: JobState
    file_name: str
    progress_percent: float
    created_at: str
