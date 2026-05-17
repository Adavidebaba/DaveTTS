/**
 * Upload Handler — Gestisce drag & drop e caricamento file .txt
 * Singola responsabilità: interazione upload e anteprima
 */
class UploadHandler {
    constructor() {
        this.dropzone = document.getElementById('dropzone');
        this.fileInput = document.getElementById('fileInput');
        this.fileInfo = document.getElementById('fileInfo');
        this.fileName = document.getElementById('fileName');
        this.fileLength = document.getElementById('fileLength');
        this.fileChunks = document.getElementById('fileChunks');
        this.fileCost = document.getElementById('fileCost');
        this.previewText = document.getElementById('previewText');
        this.btnToStep2 = document.getElementById('btnToStep2');

        this.uploadedFileId = null;
        this.onUploadSuccess = null; // callback

        this._bindEvents();
    }

    _bindEvents() {
        // Click per aprire file picker
        this.dropzone.addEventListener('click', () => {
            this.fileInput.click();
        });

        // File selezionato dal picker
        this.fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) this._handleFile(file);
        });

        // Drag & Drop
        this.dropzone.addEventListener('dragover', (event) => {
            event.preventDefault();
            this.dropzone.classList.add('drag-over');
        });

        this.dropzone.addEventListener('dragleave', () => {
            this.dropzone.classList.remove('drag-over');
        });

        this.dropzone.addEventListener('drop', (event) => {
            event.preventDefault();
            this.dropzone.classList.remove('drag-over');
            const file = event.dataTransfer.files[0];
            if (file) this._handleFile(file);
        });
    }

    async _handleFile(file) {
        // Validazione client-side
        if (!file.name.endsWith('.txt')) {
            alert('Per favore seleziona un file .txt');
            return;
        }

        if (file.size > 10 * 1024 * 1024) {
            alert('File troppo grande. Massimo 10MB.');
            return;
        }

        try {
            this._showLoading();
            const result = await this._uploadToServer(file);
            this._showFileInfo(result, file.name);
        } catch (error) {
            console.error('Errore upload:', error);
            alert('Errore durante il caricamento: ' + error.message);
        }
    }

    async _uploadToServer(file) {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Errore upload');
        }

        return await response.json();
    }

    async _showFileInfo(result, originalName) {
        this.uploadedFileId = result.file_id;

        // Mostra metadati
        this.fileName.textContent = originalName;
        this.fileLength.textContent = this._formatLength(result.text_length);
        this.fileChunks.textContent = result.estimated_chunks;

        // Calcola costo stimato
        const pricePer1m = window.daveTtsApp?.config?.price_per_1m_chars || 15.0;
        const estimatedCost = (result.text_length / 1_000_000) * pricePer1m;
        if (estimatedCost > 0 && estimatedCost < 0.01) {
            this.fileCost.textContent = '< $0.01';
        } else {
            this.fileCost.textContent = `$${estimatedCost.toFixed(2)}`;
        }

        // Carica anteprima
        await this._loadPreview(result.file_id);

        // Mostra sezione info e bottone
        this.fileInfo.classList.remove('hidden');
        this.btnToStep2.classList.remove('hidden');
        this.btnToStep2.disabled = false;

        // Callback per app.js
        if (this.onUploadSuccess) {
            this.onUploadSuccess(result);
        }
    }

    async _loadPreview(fileId) {
        try {
            const response = await fetch(`/api/preview/${fileId}`);
            const data = await response.json();
            let previewContent = data.preview;
            if (data.is_truncated) {
                previewContent += '\n\n[... testo troncato ...]';
            }
            this.previewText.textContent = previewContent;
        } catch (error) {
            this.previewText.textContent = 'Anteprima non disponibile';
        }
    }

    _showLoading() {
        this.dropzone.querySelector('.dropzone-text').textContent = 'Caricamento...';
    }

    _formatLength(chars) {
        if (chars < 1000) return `${chars} caratteri`;
        if (chars < 1_000_000) return `${(chars / 1000).toFixed(1)}K caratteri`;
        return `${(chars / 1_000_000).toFixed(1)}M caratteri`;
    }

    getFileId() {
        return this.uploadedFileId;
    }

    reset() {
        this.uploadedFileId = null;
        this.fileInfo.classList.add('hidden');
        this.btnToStep2.classList.add('hidden');
        this.btnToStep2.disabled = true;
        this.fileInput.value = '';
        this.dropzone.querySelector('.dropzone-text').textContent =
            'Trascina qui il tuo file .txt';
    }
}
