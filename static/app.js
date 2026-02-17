// IndexedDB Storage Wrapper
class ChatStorage {
    constructor() {
        this.dbName = 'PocketTTS_DB';
        this.version = 1;
        this.db = null;
        this.ready = this.init();
    }

    init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.version);

            request.onupgradeneeded = (e) => {
                const db = e.target.result;
                if (!db.objectStoreNames.contains('messages')) {
                    db.createObjectStore('messages', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('audio')) {
                    db.createObjectStore('audio', { keyPath: 'id' });
                }
            };

            request.onsuccess = (e) => {
                this.db = e.target.result;
                resolve();
            };

            request.onerror = (e) => reject(e);
        });
    }

    async getHistory() {
        await this.ready;
        return new Promise((resolve) => {
            const tx = this.db.transaction('messages', 'readonly');
            const store = tx.objectStore('messages');
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result.sort((a, b) => a.timestamp - b.timestamp));
        });
    }

    async saveMessage(msg) {
        await this.ready;
        const tx = this.db.transaction('messages', 'readwrite');
        tx.objectStore('messages').put(msg);
    }

    async saveAudio(id, blob) {
        await this.ready;
        const tx = this.db.transaction('audio', 'readwrite');
        tx.objectStore('audio').put({ id, blob });
    }

    async getAudio(id) {
        await this.ready;
        return new Promise((resolve) => {
            const tx = this.db.transaction('audio', 'readonly');
            const req = tx.objectStore('audio').get(id);
            req.onsuccess = () => resolve(req.result ? req.result.blob : null);
        });
    }
}

class ChatController {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.currentVoice = 'alba';
        this.voices = [];
        this.ctx = null; // AudioContext
        this.storage = new ChatStorage();

        this.initUI();
        this.connectWS();
        this.initAudio();
        this.loadVoices();
        this.loadHistory();
    }

    initUI() {
        // Elements
        this.el = {
            input: document.getElementById('chatInput'),
            sendBtn: document.getElementById('sendBtn'),
            messages: document.getElementById('messagesContainer'),
            charCount: document.getElementById('charCount'),
            voiceSelector: document.getElementById('voiceSelector'),
            voiceModal: document.getElementById('voiceModal'),
            voiceGrid: document.getElementById('voiceGrid'),
            closeModal: document.querySelector('.close-btn'),
            maxTokens: document.getElementById('maxTokens'),
            maxTokensVal: document.getElementById('maxTokensValue'),
            status: document.getElementById('connStatus'),
            uploadBtn: document.getElementById('uploadVoiceBtn'),
            voiceInput: document.getElementById('voiceFileInput')
        };

        // Auto-expand textarea
        this.el.input.addEventListener('input', (e) => {
            e.target.style.height = 'auto';
            e.target.style.height = e.target.scrollHeight + 'px';
            this.el.charCount.innerText = `${e.target.value.length}/1000`;
        });

        // Send on Enter (Shift+Enter for new line)
        this.el.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.el.sendBtn.addEventListener('click', () => this.sendMessage());

        // Voice Selector Modal
        this.el.voiceSelector.addEventListener('click', () => {
            this.el.voiceModal.classList.add('visible');
        });

        this.el.closeModal.addEventListener('click', () => {
            this.el.voiceModal.classList.remove('visible');
        });

        this.el.voiceModal.addEventListener('click', (e) => {
            if (e.target === this.el.voiceModal) this.el.voiceModal.classList.remove('visible');
        });

        // Sliders
        this.el.maxTokens.addEventListener('input', (e) => {
            this.el.maxTokensVal.innerText = e.target.value;
        });

        // Upload
        this.el.uploadBtn.addEventListener('click', () => this.el.voiceInput.click());
        this.el.voiceInput.addEventListener('change', (e) => {
            if (e.target.files.length) this.uploadVoice(e.target.files[0]);
        });
    }

    connectWS() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.socket = new WebSocket(`${protocol}//${window.location.host}/ws/stream`);

        this.socket.onopen = () => {
            this.isConnected = true;
            this.updateStatus(true);
        };

        this.socket.onclose = () => {
            this.isConnected = false;
            this.updateStatus(false);
            setTimeout(() => this.connectWS(), 3000);
        };

        this.socket.onmessage = (e) => this.handleMessage(JSON.parse(e.data));
    }

    updateStatus(online) {
        if (online) {
            this.el.status.innerHTML = '<span class="dot"></span> Connected';
            this.el.status.style.color = '#34d399';
        } else {
            this.el.status.innerHTML = '<span class="dot" style="background:red"></span> Disconnected';
            this.el.status.style.color = '#ef4444';
        }
    }

    initAudio() {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    }

    async loadVoices() {
        try {
            const res = await fetch('/api/voices');
            const data = await res.json();
            this.voices = data.voices;
            this.renderVoiceGrid();
        } catch (e) {
            console.error(e);
        }
    }

    renderVoiceGrid() {
        this.el.voiceGrid.innerHTML = '';
        this.voices.forEach(v => {
            const card = document.createElement('div');
            card.className = `voice-card ${v.name === this.currentVoice ? 'active' : ''}`;
            card.innerHTML = `
                <div class="voice-avatar" style="margin: 0 auto">${v.name[0]}</div>
                <span class="name">${v.name}</span>
            `;
            card.onclick = () => this.selectVoice(v);
            this.el.voiceGrid.appendChild(card);
        });
    }

    selectVoice(voice) {
        this.currentVoice = voice.name;
        this.el.voiceModal.classList.remove('visible');

        // Update sidebar display
        const display = document.getElementById('currentVoiceDisplay');
        display.querySelector('.name').innerText = voice.name;
        display.querySelector('.type').innerText = voice.type || 'Standard';
        display.querySelector('.voice-avatar').innerText = voice.name[0];

        this.renderVoiceGrid(); // to update active state
    }

    async loadHistory() {
        const history = await this.storage.getHistory();
        for (const msg of history) {
            const bubble = this.addMessageBubble(msg.role, msg.text, msg.id, true);
            if (msg.role === 'ai' && msg.audioId) {
                // Determine if we have metrics
                if (msg.metrics) {
                    // Update metrics UI immediately
                    const metrics = msg.metrics;
                    const el = bubble; // addMessageBubble returns the element
                    if (el) {
                        const lat = el.querySelector('.metric.latency .val');
                        const rtf = el.querySelector('.metric.rtf .val');
                        if (lat) lat.innerText = (metrics.first_chunk_latency * 1000).toFixed(0);
                        if (rtf) rtf.innerText = metrics.rtf.toFixed(2);
                    }
                }

                // Initialize controller for replay
                const blob = await this.storage.getAudio(msg.audioId);
                if (blob) {
                    new AudioStreamController(this.ctx, bubble, blob);
                }
            }
        }
    }

    addMessageBubble(role, text, id = null, isHistory = false) {
        const tpl = document.getElementById(role === 'user' ? 'userMessageTemplate' : 'aiAudioTemplate');
        const node = tpl.content.cloneNode(true);
        const el = node.querySelector('.message');
        el.dataset.id = id || Date.now();

        if (role === 'user') {
            el.querySelector('.text-content').innerText = text;
        } else {
            el.querySelector('.text-subtitles').innerText = text;
        }

        this.el.messages.appendChild(el);
        this.el.messages.scrollTop = this.el.messages.scrollHeight;
        return el;
    }

    sendMessage() {
        const text = this.el.input.value.trim();
        if (!text || !this.isConnected) return;

        this.el.input.value = '';
        this.el.input.style.height = 'auto'; // reset height

        const timestamp = Date.now();
        const userMsgId = 'user_' + timestamp;
        const aiMsgId = 'ai_' + timestamp;

        // Save User Message
        this.storage.saveMessage({ id: userMsgId, role: 'user', text, timestamp });
        this.addMessageBubble('user', text, userMsgId);

        // Create AI bubble
        const aiBubble = this.addMessageBubble('ai', text, aiMsgId);

        // Save AI Message Placeholder
        this.storage.saveMessage({ id: aiMsgId, role: 'ai', text, timestamp: timestamp + 1, audioId: aiMsgId });

        // Setup audio controller for this bubble
        const controller = new AudioStreamController(this.ctx, aiBubble);

        // Register current controller to receive stream
        this.currentStreamController = controller;
        this.currentAiMsgId = aiMsgId;

        // Send to server
        this.socket.send(JSON.stringify({
            text: text,
            voice: this.currentVoice,
            max_tokens: parseInt(this.el.maxTokens.value)
        }));
    }

    handleMessage(msg) {
        if (!this.currentStreamController) return;

        if (msg.type === 'audio') {
            this.currentStreamController.feed(msg.data);
        } else if (msg.type === 'done') {
            const blob = this.currentStreamController.finish(msg.metrics);

            // Save Audio Blob
            if (blob && this.currentAiMsgId) {
                this.storage.saveAudio(this.currentAiMsgId, blob);
                // Update message with metrics
                this.storage.saveMessage({
                    id: this.currentAiMsgId,
                    role: 'ai',
                    text: document.querySelector(`[data-id="${this.currentAiMsgId}"] .text-subtitles`).innerText,
                    timestamp: Date.now(),
                    audioId: this.currentAiMsgId,
                    metrics: msg.metrics
                });
            }
            this.currentStreamController = null;
        } else if (msg.type === 'error') {
            alert('Error: ' + msg.message);
        }
    }

    async uploadVoice(file) {
        const formData = new FormData();
        formData.append('file', file);
        try {
            await fetch('/api/upload-voice', { method: 'POST', body: formData });
            alert('Voice uploaded!');
            this.loadVoices();
        } catch (e) {
            alert('Upload failed');
        }
    }
}

// Handles audio streaming/playback for a single message bubble
class AudioStreamController {
    constructor(ctx, element, existingBlob = null) {
        this.ctx = ctx;
        this.element = element;
        this.queue = [];
        this.nextStartTime = 0;
        this.isPlaying = false;
        this.audioChunks = []; // Store chunks for blob creation
        this.existingBlob = existingBlob;

        this.ui = {
            playBtn: element.querySelector('.play-btn'),
            canvas: element.querySelector('.waveform'),
            time: element.querySelector('.time'),
            metrics: element.querySelector('.metrics'),
            downloadBtn: element.querySelector('.download-btn')
        };

        this.canvasCtx = this.ui.canvas.getContext('2d');
        this.analyser = this.ctx.createAnalyser();
        this.analyser.fftSize = 256;

        // Resize canvas
        this.resizeCanvas();
        // Removed global resize listener for simplicity/performance in this snippet, can re-add if needed
        // window.addEventListener('resize', () => this.resizeCanvas());

        this.startVisualizer();

        // Play Button Logic
        this.ui.playBtn.onclick = () => this.togglePlay();

        // Download Button Logic
        if (this.existingBlob) {
            this.setupDownload(this.existingBlob);
        }
    }

    setupDownload(blob) {
        const url = URL.createObjectURL(blob);
        this.ui.downloadBtn.onclick = () => {
            const a = document.createElement('a');
            a.href = url;
            a.download = `pocket_tts_${Date.now()}.wav`; // simple wav ext
            a.click();
        };
    }

    async togglePlay() {
        if (this.isPlaying) return; // Simple "play" only for now, pause is complex with WebAudio

        this.isPlaying = true;
        this.ui.playBtn.innerHTML = '<i class="ri-stop-fill"></i>';

        // If we have a blob (replay), decode it
        if (this.existingBlob) {
            const arrayBuffer = await this.existingBlob.arrayBuffer();
            const audioBuffer = await this.ctx.decodeAudioData(arrayBuffer);
            this.playBuffer(audioBuffer);
        } else {
            // Currently streaming, already playing
        }
    }

    playBuffer(buffer) {
        const source = this.ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(this.analyser);
        this.analyser.connect(this.ctx.destination);
        source.onended = () => {
            this.isPlaying = false;
            this.ui.playBtn.innerHTML = '<i class="ri-play-fill"></i>';
        };
        source.start();
    }

    resizeCanvas() {
        if (this.ui.canvas) {
            const rect = this.ui.canvas.parentElement.getBoundingClientRect();
            this.ui.canvas.width = rect.width;
            this.ui.canvas.height = rect.height;
        }
    }

    feed(chunk) {
        // Convert to Float32
        const float32 = new Float32Array(chunk);
        this.audioChunks.push(float32); // Store for blob

        const buffer = this.ctx.createBuffer(1, float32.length, this.ctx.sampleRate);
        buffer.getChannelData(0).set(float32);

        this.queueAudio(buffer);
    }

    queueAudio(buffer) {
        const source = this.ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(this.analyser); // Connect to visualizer
        this.analyser.connect(this.ctx.destination);

        // Schedule
        const now = this.ctx.currentTime;
        if (this.nextStartTime < now) this.nextStartTime = now + 0.1; // Jitter buffer

        source.start(this.nextStartTime);
        this.nextStartTime += buffer.duration;
    }

    finish(metrics) {
        if (this.ui.metrics) { // Update metrics if UI exists
            const lat = this.element.querySelector('.metric.latency .val');
            const rtf = this.element.querySelector('.metric.rtf .val');
            if (lat) lat.innerText = (metrics.first_chunk_latency * 1000).toFixed(0);
            if (rtf) rtf.innerText = metrics.rtf.toFixed(2);
        }

        // Create Blob from chunks for download/replay
        // Note: Raw Float32 chunks to WAV is complex in JS without library. 
        // For MVP, we'll skip proper WAV encoding in frontend and just save raw or use a simple wav header injector.
        // Actually, we can use a simple wav encoder function.
        const blob = this.createWavBlob(this.audioChunks);
        this.existingBlob = blob;
        this.setupDownload(blob);
        return blob;
    }

    createWavBlob(chunks) {
        // Flatten
        let length = 0;
        chunks.forEach(c => length += c.length);
        const float32 = new Float32Array(length);
        let offset = 0;
        chunks.forEach(c => {
            float32.set(c, offset);
            offset += c.length;
        });

        return this.encodeWAV(float32, 24000);
    }

    encodeWAV(samples, sampleRate) {
        const buffer = new ArrayBuffer(44 + samples.length * 2);
        const view = new DataView(buffer);
        const writeString = (view, offset, string) => {
            for (let i = 0; i < string.length; i++) view.setUint8(offset + i, string.charCodeAt(i));
        };

        writeString(view, 0, 'RIFF');
        view.setUint32(4, 36 + samples.length * 2, true);
        writeString(view, 8, 'WAVE');
        writeString(view, 12, 'fmt ');
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, 1, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, sampleRate * 2, true);
        view.setUint16(32, 2, true);
        view.setUint16(34, 16, true);
        writeString(view, 36, 'data');
        view.setUint32(40, samples.length * 2, true);

        const volume = 1;
        let index = 44;
        for (let i = 0; i < samples.length; i++) {
            let s = Math.max(-1, Math.min(1, samples[i]));
            s = s < 0 ? s * 0x8000 : s * 0x7FFF;
            view.setInt16(index, s, true);
            index += 2;
        }

        return new Blob([view], { type: 'audio/wav' });
    }

    startVisualizer() {
        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        const ctx = this.canvasCtx;

        const draw = () => {
            if (!this.ui.canvas) return; // Safety
            const w = this.ui.canvas.width;
            const h = this.ui.canvas.height;
            requestAnimationFrame(draw);

            this.analyser.getByteFrequencyData(dataArray);

            ctx.fillStyle = '#161925'; // Clear with bg color
            ctx.fillRect(0, 0, w, h);

            const barWidth = (w / bufferLength) * 2.5;
            let barHeight;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                barHeight = dataArray[i] / 2;

                // Gradient color
                ctx.fillStyle = `rgb(${barHeight + 100}, 99, 241)`;
                ctx.fillRect(x, h - barHeight, barWidth, barHeight);

                x += barWidth + 1;
            }
        };

        draw();
    }
}

document.addEventListener('DOMContentLoaded', () => new ChatController());
