"""
Cataloghi voci per tutti i provider TTS supportati.
Ogni provider ha il proprio catalogo con metadati per l'UI.
"""


class XaiVoiceCatalog:
    """Catalogo voci disponibili dall'API xAI TTS."""

    PROVIDER_ID = "xai"
    PROVIDER_LABEL = "xAI (Grok)"

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


class GeminiVoiceCatalog:
    """Catalogo voci disponibili dall'API Google Gemini TTS."""

    PROVIDER_ID = "gemini"
    PROVIDER_LABEL = "Google Gemini"

    VOICES = {
        "Kore": {
            "name": "Kore",
            "description": "Sicura e professionale",
            "icon": "🏛️",
        },
        "Puck": {
            "name": "Puck",
            "description": "Energica e vivace",
            "icon": "⚡",
        },
        "Charon": {
            "name": "Charon",
            "description": "Calma e informativa",
            "icon": "📰",
        },
        "Aoede": {
            "name": "Aoede",
            "description": "Naturale e calda",
            "icon": "🌿",
        },
        "Fenrir": {
            "name": "Fenrir",
            "description": "Dinamico ed espressivo",
            "icon": "🐺",
        },
        "Zephyr": {
            "name": "Zephyr",
            "description": "Luminosa e allegra",
            "icon": "🌤️",
        },
        "Leda": {
            "name": "Leda",
            "description": "Elegante e raffinata",
            "icon": "🦢",
        },
        "Orus": {
            "name": "Orus",
            "description": "Profonda e risonante",
            "icon": "🔮",
        },
        "Achernar": {
            "name": "Achernar",
            "description": "Brillante e chiara",
            "icon": "⭐",
        },
        "Enceladus": {
            "name": "Enceladus",
            "description": "Morbida e rilassata",
            "icon": "❄️",
        },
        "Iapetus": {
            "name": "Iapetus",
            "description": "Solida e decisa",
            "icon": "🪨",
        },
        "Umbriel": {
            "name": "Umbriel",
            "description": "Misteriosa e profonda",
            "icon": "🌑",
        },
        "Algieba": {
            "name": "Algieba",
            "description": "Melodica e fluida",
            "icon": "🎶",
        },
        "Despina": {
            "name": "Despina",
            "description": "Dolce e accogliente",
            "icon": "🌊",
        },
        "Erinome": {
            "name": "Erinome",
            "description": "Intensa e coinvolgente",
            "icon": "🔥",
        },
        "Gacrux": {
            "name": "Gacrux",
            "description": "Stabile e rassicurante",
            "icon": "✦",
        },
        "Pulcherrima": {
            "name": "Pulcherrima",
            "description": "Elegante e armoniosa",
            "icon": "💎",
        },
        "Rasalgethi": {
            "name": "Rasalgethi",
            "description": "Gravosa e autorevole",
            "icon": "🛡️",
        },
        "Laomedeia": {
            "name": "Laomedeia",
            "description": "Fluida e serena",
            "icon": "🌙",
        },
        "Sulafat": {
            "name": "Sulafat",
            "description": "Vivida e articolata",
            "icon": "🎯",
        },
        "Vindemiatrix": {
            "name": "Vindemiatrix",
            "description": "Pacata e riflessiva",
            "icon": "🍇",
        },
        "Sadachbia": {
            "name": "Sadachbia",
            "description": "Ottimista e gentile",
            "icon": "🌈",
        },
        "Schedar": {
            "name": "Schedar",
            "description": "Chiara e precisa",
            "icon": "💫",
        },
        "Zubenelgenubi": {
            "name": "Zubenelgenubi",
            "description": "Bilanciata e versatile",
            "icon": "⚖️",
        },
        "Autonoe": {
            "name": "Autonoe",
            "description": "Fresca e spontanea",
            "icon": "🌻",
        },
        "Callirrhoe": {
            "name": "Callirrhoe",
            "description": "Delicata e melodiosa",
            "icon": "🎵",
        },
        "Achird": {
            "name": "Achird",
            "description": "Nitida e dinamica",
            "icon": "🌟",
        },
        "Algenib": {
            "name": "Algenib",
            "description": "Ferma e composta",
            "icon": "🏔️",
        },
        "Alnilam": {
            "name": "Alnilam",
            "description": "Calda e avvolgente",
            "icon": "🔆",
        },
        "Sadaltager": {
            "name": "Sadaltager",
            "description": "Tranquilla e costante",
            "icon": "🌾",
        },
    }

    @classmethod
    def is_valid(cls, voice_id: str) -> bool:
        return voice_id in cls.VOICES

    @classmethod
    def get_all(cls) -> dict:
        return cls.VOICES


def get_voice_catalog(provider: str):
    """Factory: ritorna il catalogo voci per il provider specificato."""
    catalogs = {
        "xai": XaiVoiceCatalog,
        "gemini": GeminiVoiceCatalog,
    }
    catalog = catalogs.get(provider)
    if not catalog:
        raise ValueError(f"Provider TTS sconosciuto: {provider}")
    return catalog
