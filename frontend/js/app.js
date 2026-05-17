/**
 * App — Coordinatore principale dell'applicazione
 * Gestisce navigazione tra step, inizializzazione moduli, e configurazione
 */
class App {
    constructor() {
        // Moduli
        this.uploadHandler = new UploadHandler();
        this.generationController = new GenerationController();
        this.audioPlayer = new AudioPlayerController();

        // Stato
        this.currentStep = 1;
        this.selectedVoice = null;
        this.selectedFormat = 'standard';
        this.selectedProvider = 'gemini';
        this.config = null;

        this._init();
    }

    async _init() {
        await this._loadConfig();
        this._buildProviderGrid();
        this._buildVoiceGrid();
        this._buildFormatGrid();
        this._bindNavigation();
        this._bindCallbacks();
    }

    async _loadConfig() {
        try {
            const response = await fetch('/api/config');
            this.config = await response.json();
            this.selectedProvider = this.config.provider || 'gemini';

            // Imposta voce default per il provider
            this._setDefaultVoice();

            // Mostra warning se nessun provider configurato
            if (!this.config.api_key_configured) {
                document.getElementById('apiKeyWarning').classList.remove('hidden');
            }
        } catch (error) {
            console.error('Errore caricamento config:', error);
        }
    }

    _setDefaultVoice() {
        const voices = this.config?.voices || {};
        const voiceIds = Object.keys(voices);
        if (voiceIds.length > 0) {
            // Seleziona la prima voce come default
            this.selectedVoice = voiceIds[0];
        }
    }

    _buildProviderGrid() {
        const grid = document.getElementById('providerGrid');
        const providers = this.config?.providers || {};

        grid.innerHTML = '';

        const providerIcons = { xai: '🤖', gemini: '💎' };

        for (const [providerId, providerInfo] of Object.entries(providers)) {
            const card = document.createElement('div');
            const isSelected = providerId === this.selectedProvider;
            const isConfigured = providerInfo.configured;

            card.className = `provider-card${isSelected ? ' selected' : ''}${!isConfigured ? ' disabled' : ''}`;
            card.dataset.providerId = providerId;
            card.innerHTML = `
                <div class="provider-card-icon">${providerIcons[providerId] || '🔧'}</div>
                <div class="provider-card-name">${providerInfo.label}</div>
                ${!isConfigured ? '<div class="provider-card-status">⚠️ Non configurato</div>' : ''}
            `;

            if (isConfigured) {
                card.addEventListener('click', () => this._selectProvider(providerId));
            }

            grid.appendChild(card);
        }
    }

    async _selectProvider(providerId) {
        if (providerId === this.selectedProvider) return;

        this.selectedProvider = providerId;

        // Aggiorna stile card provider
        document.querySelectorAll('.provider-card').forEach(card => {
            card.classList.toggle('selected', card.dataset.providerId === providerId);
        });

        // Carica voci del nuovo provider
        await this._loadProviderVoices(providerId);
    }

    async _loadProviderVoices(providerId) {
        try {
            const response = await fetch(`/api/config?provider=${providerId}`);
            const providerConfig = await response.json();

            // Aggiorna voci e costo nella config locale
            this.config.voices = providerConfig.voices;
            this.config.price_per_1m_chars = providerConfig.price_per_1m_chars;

            // Seleziona la prima voce del nuovo provider
            this._setDefaultVoice();

            // Ricostruisci la griglia voci
            this._buildVoiceGrid();

            // Mostra/nascondi sezione lingua
            this._updateLanguageVisibility();
        } catch (error) {
            console.error('Errore caricamento voci provider:', error);
        }
    }

    _updateLanguageVisibility() {
        const langSection = document.getElementById('languageSection');
        if (langSection) {
            // Gemini fa auto-detect, la lingua serve solo per xAI
            if (this.selectedProvider === 'gemini') {
                langSection.classList.add('hidden');
            } else {
                langSection.classList.remove('hidden');
            }
        }
    }

    _buildVoiceGrid() {
        const grid = document.getElementById('voiceGrid');
        const voices = this.config?.voices || {};

        grid.innerHTML = '';

        for (const [voiceId, voice] of Object.entries(voices)) {
            const card = document.createElement('div');
            card.className = `voice-card${voiceId === this.selectedVoice ? ' selected' : ''}`;
            card.dataset.voiceId = voiceId;
            card.innerHTML = `
                <div class="voice-card-icon">${voice.icon}</div>
                <div class="voice-card-name">${voice.name}</div>
                <div class="voice-card-desc">${voice.description}</div>
            `;
            card.addEventListener('click', () => this._selectVoice(voiceId));
            grid.appendChild(card);
        }
    }

    _buildFormatGrid() {
        const grid = document.getElementById('formatGrid');
        const formats = this.config?.output_formats || {
            standard: { label: 'MP3 Standard (44.1 kHz, 128 kbps)' },
            high: { label: 'MP3 Alta Qualità (44.1 kHz, 192 kbps)' },
            low: { label: 'MP3 Leggero (24 kHz, 128 kbps)' },
        };

        grid.innerHTML = '';

        for (const [formatId, format] of Object.entries(formats)) {
            const card = document.createElement('div');
            card.className = `format-card${formatId === this.selectedFormat ? ' selected' : ''}`;
            card.dataset.formatId = formatId;
            card.innerHTML = `<div class="format-card-label">${format.label}</div>`;
            card.addEventListener('click', () => this._selectFormat(formatId));
            grid.appendChild(card);
        }
    }

    _selectVoice(voiceId) {
        this.selectedVoice = voiceId;
        document.querySelectorAll('.voice-card').forEach(card => {
            card.classList.toggle('selected', card.dataset.voiceId === voiceId);
        });
    }

    _selectFormat(formatId) {
        this.selectedFormat = formatId;
        document.querySelectorAll('.format-card').forEach(card => {
            card.classList.toggle('selected', card.dataset.formatId === formatId);
        });
    }

    _bindNavigation() {
        // Step 1 → Step 2
        document.getElementById('btnToStep2').addEventListener('click', () => {
            this._goToStep(2);
            this._updateLanguageVisibility();
        });

        // Step 2 → Step 1
        document.getElementById('btnBackToStep1').addEventListener('click', () => {
            this._goToStep(1);
        });

        // Step 2 → Step 3 (avvia generazione)
        document.getElementById('btnToStep3').addEventListener('click', () => {
            this._startGeneration();
        });

        // Step 3 → Step 2
        document.getElementById('btnBackToStep2').addEventListener('click', () => {
            this._goToStep(2);
        });

        // Nuovo libro
        document.getElementById('btnNewBook').addEventListener('click', () => {
            this._resetAll();
        });

        // Retry
        document.getElementById('btnRetry').addEventListener('click', () => {
            this._startGeneration();
        });

        // Resume (riprendi dopo pausa/credito esaurito)
        document.getElementById('btnResume').addEventListener('click', () => {
            this.generationController.resumeGeneration();
        });

        // Modal close
        document.getElementById('btnCloseModal').addEventListener('click', () => {
            document.getElementById('apiKeyWarning').classList.add('hidden');
        });
    }

    _bindCallbacks() {
        // Quando upload completato
        this.uploadHandler.onUploadSuccess = () => {
            // Il bottone viene già abilitato dall'upload handler
        };

        // Quando generazione completata
        this.generationController.onComplete = (jobId) => {
            this.audioPlayer.loadAudiobook(jobId);
        };
    }

    _goToStep(step) {
        this.currentStep = step;

        // Aggiorna indicatori step
        document.querySelectorAll('.step').forEach(stepEl => {
            const stepNum = parseInt(stepEl.dataset.step);
            stepEl.classList.remove('active', 'completed');
            if (stepNum === step) stepEl.classList.add('active');
            if (stepNum < step) stepEl.classList.add('completed');
        });

        // Mostra pannello corretto
        document.querySelectorAll('.step-panel').forEach(panel => {
            panel.classList.remove('active');
        });
        document.getElementById(`step${step}Panel`).classList.add('active');
    }

    async _startGeneration() {
        const fileId = this.uploadHandler.getFileId();
        if (!fileId) {
            alert('Nessun file caricato');
            return;
        }

        const language = document.getElementById('languageSelect').value;

        this._goToStep(3);

        // Nascondi bottone indietro durante la generazione
        document.getElementById('btnBackToStep2').classList.add('hidden');

        await this.generationController.startGeneration(
            fileId,
            this.selectedVoice,
            language,
            this.selectedFormat,
            this.selectedProvider,
        );
    }

    _resetAll() {
        this.uploadHandler.reset();
        this.audioPlayer.reset();
        this.generationController.destroy();
        this.generationController = new GenerationController();
        this._bindCallbacks();
        this._goToStep(1);
    }
}

// Avvio applicazione
document.addEventListener('DOMContentLoaded', () => {
    window.daveTtsApp = new App();
});
