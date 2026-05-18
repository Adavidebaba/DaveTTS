/**
 * Generation Controller — Avvia la generazione e traccia il progresso
 * Singola responsabilità: comunicazione API generazione + polling stato
 */
class GenerationController {
    constructor() {
        this.progressFill = document.getElementById('progressFill');
        this.progressPercent = document.getElementById('progressPercent');
        this.progressChunks = document.getElementById('progressChunks');
        this.progressState = document.getElementById('progressState');
        this.generationStatus = document.getElementById('generationStatus');
        this.progressContainer = document.getElementById('progressContainer');
        this.errorBox = document.getElementById('errorBox');
        this.errorMessage = document.getElementById('errorMessage');
        this.resultContainer = document.getElementById('resultContainer');

        this.currentJobId = null;
        this.pollingInterval = null;
        this.onComplete = null; // callback(jobId)
        this.onError = null;   // callback(message)
        this.onPaused = null;  // callback(message)

        this.POLL_INTERVAL_MS = 2000;
    }

    async startGeneration(fileId, voiceId, language, outputFormat, provider, promptData = null, previewOnly = true) {
        this._resetUI();

        try {
            const bodyData = {
                file_id: fileId,
                voice_id: voiceId,
                language: language,
                output_format: outputFormat,
                provider: provider || 'gemini',
            };
            
            if (promptData) {
                bodyData.prompt_data = promptData;
            }
            bodyData.preview_only = previewOnly;

            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(bodyData),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Errore avvio generazione');
            }

            const data = await response.json();
            this.currentJobId = data.job_id;

            this._startPolling();
        } catch (error) {
            this._showError(error.message);
        }
    }

    _startPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        this.pollingInterval = setInterval(
            () => this._pollStatus(),
            this.POLL_INTERVAL_MS
        );
    }

    _stopPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    async _pollStatus() {
        if (!this.currentJobId) return;

        try {
            const response = await fetch(`/api/status/${this.currentJobId}`);
            if (!response.ok) return;

            const status = await response.json();
            this._updateProgress(status);

            if (status.state === 'completed') {
                this._stopPolling();
                this._showResult();
            } else if (status.state === 'paused') {
                this._stopPolling();
                this._showPaused(status);
            } else if (status.state === 'review') {
                this._stopPolling();
                this._showReview();
            } else if (status.state === 'error' || status.state === 'cancelled') {
                this._stopPolling();
                this._showError(
                    status.error_message || 'Generazione interrotta',
                    status.is_resumable,
                );
            }
        } catch (error) {
            console.error('Errore polling:', error);
        }
    }

    _updateProgress(status) {
        const percent = status.progress_percent || 0;

        this.progressFill.style.width = `${percent}%`;
        this.progressPercent.textContent = `${percent.toFixed(1)}%`;
        this.progressChunks.textContent =
            `${status.chunks_completed} / ${status.chunks_total} chunk`;

        const stateLabels = {
            pending: '⏳ In attesa...',
            splitting: '✂️ Suddivisione testo...',
            generating: '🎙️ Generazione audio in corso...',
            merging: '🔗 Unione dei frammenti audio...',
            completed: '✅ Completato!',
            paused: '⏸️ In pausa — credito esaurito',
            error: '❌ Errore',
            cancelled: '⏹️ Interrotto',
        };

        this.progressState.textContent =
            stateLabels[status.state] || status.state;
        this.generationStatus.textContent =
            stateLabels[status.state] || 'Elaborazione...';
    }

    _showResult() {
        this.progressContainer.classList.add('hidden');
        this.resultContainer.classList.remove('hidden');
        this.generationStatus.textContent = '✅ Audiolibro completato!';

        if (this.onComplete) {
            this.onComplete(this.currentJobId);
        }
        document.getElementById('btnStopGeneration').classList.add('hidden');
        document.getElementById('btnBackToStep2').classList.remove('hidden');
    }

    _showReview() {
        this.progressContainer.classList.add('hidden');
        document.getElementById('previewContainer').classList.remove('hidden');
        this.generationStatus.textContent = '🎧 Anteprima pronta';

        const previewAudio = document.getElementById('previewAudioPlayer');
        previewAudio.src = `/api/audio_preview/${this.currentJobId}?t=${new Date().getTime()}`;

        document.getElementById('btnStopGeneration').classList.add('hidden');
        document.getElementById('btnBackToStep2').classList.remove('hidden');
    }

    _showPaused(status) {
        this.progressContainer.classList.add('hidden');
        this.errorBox.classList.remove('hidden');
        this.errorMessage.textContent =
            status.error_message || 'Credito API esaurito';
        this.generationStatus.textContent =
            '⏸️ In pausa — ricarica il credito API';

        // Mostra bottone riprendi
        const btnResume = document.getElementById('btnResume');
        const btnRetry = document.getElementById('btnRetry');
        if (btnResume) btnResume.classList.remove('hidden');
        if (btnRetry) btnRetry.classList.add('hidden');

        if (this.onPaused) {
            this.onPaused(status.error_message);
        }

        document.getElementById('btnStopGeneration').classList.add('hidden');
        document.getElementById('btnBackToStep2').classList.remove('hidden');
    }

    _showError(message, isResumable = false) {
        this.progressContainer.classList.add('hidden');
        this.errorBox.classList.remove('hidden');
        this.errorMessage.textContent = message;
        this.generationStatus.textContent =
            '❌ Errore durante la generazione';

        // Mostra bottone appropriato
        const btnResume = document.getElementById('btnResume');
        const btnRetry = document.getElementById('btnRetry');
        if (btnResume) {
            btnResume.classList.toggle('hidden', !isResumable);
        }
        if (btnRetry) {
            btnRetry.classList.toggle('hidden', isResumable);
        }

        if (this.onError) {
            this.onError(message);
        }

        document.getElementById('btnStopGeneration').classList.add('hidden');
        document.getElementById('btnBackToStep2').classList.remove('hidden');
    }

    async resumeGeneration() {
        if (!this.currentJobId) return;

        this._resetUI();
        this.generationStatus.textContent =
            '🔄 Ripresa generazione in corso...';

        try {
            const response = await fetch(
                `/api/resume/${this.currentJobId}`,
                { method: 'POST' },
            );

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(
                    errorData.detail || 'Errore ripresa generazione',
                );
            }

            this._startPolling();
        } catch (error) {
            this._showError(error.message);
        }
    }

    async cancelGeneration() {
        if (!this.currentJobId) return;
        
        try {
            const response = await fetch(`/api/cancel/${this.currentJobId}`, {
                method: 'POST'
            });
            if (!response.ok) {
                const errorData = await response.json();
                console.error("Impossibile annullare:", errorData.detail);
            }
            // Il polling catturerà lo stato 'cancelled' al prossimo ciclo
        } catch (error) {
            console.error('Errore annullamento generazione:', error);
        }
    }

    _resetUI() {
        this.progressFill.style.width = '0%';
        this.progressPercent.textContent = '0%';
        this.progressChunks.textContent = '0 / 0 chunk';
        this.progressState.textContent = '';
        this.generationStatus.textContent = 'Preparazione...';
        this.progressContainer.classList.remove('hidden');
        this.errorBox.classList.add('hidden');
        this.resultContainer.classList.add('hidden');
        
        const previewContainer = document.getElementById('previewContainer');
        if (previewContainer) {
            previewContainer.classList.add('hidden');
        }

        document.getElementById('btnStopGeneration').classList.remove('hidden');
        document.getElementById('btnBackToStep2').classList.add('hidden');
    }

    getJobId() {
        return this.currentJobId;
    }

    destroy() {
        this._stopPolling();
    }
}
