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
        this.selectedVoice = 'leo';
        this.selectedFormat = 'standard';
        this.config = null;

        this._init();
    }

    async _init() {
        await this._loadConfig();
        this._buildVoiceGrid();
        this._buildFormatGrid();
        this._bindNavigation();
        this._bindCallbacks();
    }

    async _loadConfig() {
        try {
            const response = await fetch('/api/config');
            this.config = await response.json();

            // Mostra warning se API key non configurata
            if (!this.config.api_key_configured) {
                document.getElementById('apiKeyWarning').classList.remove('hidden');
            }
        } catch (error) {
            console.error('Errore caricamento config:', error);
        }
    }

    _buildVoiceGrid() {
        const grid = document.getElementById('voiceGrid');
        const voices = this.config?.voices || {
            leo: { name: 'Leo', description: 'Autorevole e forte', icon: '🦁' },
            eve: { name: 'Eve', description: 'Energica e vivace', icon: '✨' },
            ara: { name: 'Ara', description: 'Calda e amichevole', icon: '🌸' },
            rex: { name: 'Rex', description: 'Sicuro e chiaro', icon: '👑' },
            sal: { name: 'Sal', description: 'Morbido e bilanciato', icon: '🎵' },
        };

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
