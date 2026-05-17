# Changelog - DaveTTS

## [1.1.0] - 2026-05-17
### Google Gemini TTS
- **Dual Provider**: Supporto sia xAI che Google Gemini TTS, selezionabile da dropdown nel frontend.
- **Gemini 3.1 Flash TTS**: Modello `gemini-3.1-flash-tts-preview` con 30 voci, auto-detect lingua, conversione PCM→MP3.
- **Factory Pattern**: `tts_provider.py` seleziona il client corretto; `voice_catalog.py` gestisce i cataloghi voci separati.
- **Resume compatibile**: Il campo `provider` è persistito nel job per riprendere con il provider corretto.
- **Costo $0**: Gemini free tier, il costo stimato si aggiorna dinamicamente in base al provider scelto.

## [1.0.0] - 2026-05-17
### Funzionalità Iniziali
- **xAI TTS Integration**: Generazione di audiolibri di alta qualità a partire da file di testo tramite l'API di xAI.
- **Resumable Audiobooks**: Ripresa automatica di conversioni interrotte grazie al salvataggio dei chunk su disco e tracciamento dello stato.
- **Cost Calculator**: Stima dei costi e dei token consumati in tempo reale durante la generazione.
- **Premium UI**: Interfaccia utente raffinata, fluida e responsive con gestione dei download e riproduttore audio integrato.
- **Docker Ready**: Configurazione Docker e Docker Compose ottimizzata per macOS e Synology NAS.
