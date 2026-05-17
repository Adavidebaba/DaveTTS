/**
 * Audio Player — Gestisce playback e download dell'audiolibro
 * Singola responsabilità: player audio e download
 */
class AudioPlayerController {
    constructor() {
        this.audioPlayer = document.getElementById('audioPlayer');
        this.btnDownload = document.getElementById('btnDownload');

        this.currentJobId = null;

        this._bindEvents();
    }

    _bindEvents() {
        this.btnDownload.addEventListener('click', () => {
            this._downloadAudiobook();
        });
    }

    loadAudiobook(jobId) {
        this.currentJobId = jobId;

        // Imposta la sorgente audio per lo streaming nel player
        const audioUrl = `/api/download/${jobId}`;
        this.audioPlayer.src = audioUrl;
        this.audioPlayer.load();
    }

    _downloadAudiobook() {
        if (!this.currentJobId) return;

        const downloadUrl = `/api/download/${this.currentJobId}`;

        // Crea link temporaneo per forzare il download
        const tempLink = document.createElement('a');
        tempLink.href = downloadUrl;
        tempLink.download = 'audiobook.mp3';
        document.body.appendChild(tempLink);
        tempLink.click();
        document.body.removeChild(tempLink);
    }

    reset() {
        this.currentJobId = null;
        this.audioPlayer.src = '';
        this.audioPlayer.load();
    }
}
