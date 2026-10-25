const API_BASE = '/api';

// Enforce Pure Light Mode Only
const body = document.body;
body.removeAttribute('data-theme');
localStorage.removeItem('theme');

// Toast Notifications
function showToast(message, type = 'success') {
    const toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) return;
    
    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'success' ? 'bg-success text-white' : type === 'error' ? 'bg-danger text-white' : 'bg-primary text-white';
    
    const toastHTML = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${bgClass}">
                <strong class="me-auto">FAQForge</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    const toastEl = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    
    toastEl.addEventListener('hidden.bs.toast', () => {
        toastEl.remove();
    });
}

// Engine Status Check
async function checkEngineStatus() {
    const statusText = document.getElementById('engineStatusText');
    const statusDot = document.getElementById('engineStatusDot');
    const activeName = document.getElementById('activeEngineName');
    const activeDesc = document.getElementById('activeEngineDesc');
    
    if (!statusText && !activeName) return;

    try {
        const res = await fetch(`${API_BASE}/ollama/status`);
        if (res.ok) {
            const data = await res.json();
            const isOllamaReady = (data.ollama_running && data.model_ready) || data.primary_engine === 'Ollama' || (data.running && data.status === 'ready');
            const model = data.configured_model || data.model || (data.installed_models && data.installed_models[0]?.name) || 'qwen2.5:3b';

            const sideStatus = document.getElementById('sidebarEngineStatus');
            if (isOllamaReady) {
                if (statusText) statusText.textContent = `Ollama: ${model}`;
                if (statusDot) {
                    statusDot.style.backgroundColor = '#10b981'; // Green
                    statusDot.title = 'Local Ollama engine running with GPU acceleration';
                }
                if (activeName) activeName.textContent = `Ollama (${model})`;
                if (activeDesc) activeDesc.textContent = `High-precision offline LLM ready`;
                if (sideStatus) sideStatus.innerHTML = `<i class="bi bi-circle-fill text-success me-1"></i> Ollama (${model})`;
            } else if (data.ollama_running || data.running) {
                if (statusText) statusText.textContent = `Ollama (${model} pulling...)`;
                if (statusDot) {
                    statusDot.style.backgroundColor = '#f59e0b'; // Amber
                    statusDot.title = 'Ollama running, model downloading';
                }
                if (activeName) activeName.textContent = `Ollama (${model})`;
                if (activeDesc) activeDesc.textContent = `Model download in progress`;
                if (sideStatus) sideStatus.innerHTML = `<i class="bi bi-circle-fill text-warning me-1"></i> Ollama (${model})`;
            } else {
                if (statusText) statusText.textContent = 'Neural Fallback (Flan-T5)';
                if (statusDot) {
                    statusDot.style.backgroundColor = '#3b82f6'; // Blue
                    statusDot.title = 'Local Neural Fallback active';
                }
                if (activeName) activeName.textContent = 'Flan-T5 (Neural Fallback)';
                if (activeDesc) activeDesc.textContent = 'Local offline model ready';
                if (sideStatus) sideStatus.innerHTML = `<i class="bi bi-circle-fill text-primary me-1"></i> Flan-T5 Fallback`;
            }
        } else {
            if (statusText) statusText.textContent = 'Neural Fallback Ready';
            if (statusDot) statusDot.style.backgroundColor = '#3b82f6';
            if (activeName) activeName.textContent = 'Flan-T5 Neural Model';
            if (activeDesc) activeDesc.textContent = 'Offline transformer engine ready';
        }
    } catch (e) {
        if (statusText) statusText.textContent = 'Local AI Ready';
        if (statusDot) statusDot.style.backgroundColor = '#10b981';
        if (activeName) activeName.textContent = 'Local AI Engine';
        if (activeDesc) activeDesc.textContent = '100% offline inference';
    }
}

// Call on startup
checkEngineStatus();

// Upload Handling
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const uploadForm = document.getElementById('uploadForm');
const generateBtn = document.getElementById('generateBtn');
const processingScreen = document.getElementById('processingScreen');
const dashboardContent = document.getElementById('dashboardContent');

if (uploadZone) {
    uploadZone.addEventListener('click', () => fileInput.click());
    
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });
    
    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });
    
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            handleFileSelect();
        }
    });
    
    fileInput.addEventListener('change', handleFileSelect);
}

function handleFileSelect() {
    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        const sizeText = file.size > 1024 * 1024 ? `${sizeMb} MB` : `${Math.round(file.size / 1024)} KB`;
        const displayEl = document.getElementById('fileNameDisplay');
        if (displayEl) {
            displayEl.innerHTML = `
                <div class="selected-file-box">
                    <div class="d-flex align-items-center text-truncate me-2">
                        <i class="bi bi-file-earmark-check text-primary fs-5 me-2"></i>
                        <span class="text-truncate">${file.name}</span>
                    </div>
                    <div class="d-flex align-items-center gap-2">
                        <span class="badge" style="background-color: var(--primary-border); color: var(--primary); font-size: 11px;">${sizeText}</span>
                        <button type="button" class="btn btn-sm btn-link text-muted p-0" onclick="clearSelectedFile(event)" title="Remove file"><i class="bi bi-x-circle"></i></button>
                    </div>
                </div>
            `;
        }
    }
}

window.clearSelectedFile = (e) => {
    if (e) e.stopPropagation();
    fileInput.value = '';
    const displayEl = document.getElementById('fileNameDisplay');
    if (displayEl) displayEl.innerHTML = '';
};

// Live character and word counter for textInput
const textInputEl = document.getElementById('textInput');
const textCharCountEl = document.getElementById('textCharCount');
if (textInputEl && textCharCountEl) {
    textInputEl.addEventListener('input', () => {
        const len = textInputEl.value.length;
        const words = textInputEl.value.trim() ? textInputEl.value.trim().split(/\s+/).length : 0;
        textCharCountEl.textContent = `${len.toLocaleString()} characters · ${words.toLocaleString()} words`;
    });
}

if (generateBtn) {
    generateBtn.addEventListener('click', async () => {
        const file = fileInput.files[0];
        const text = document.getElementById('textInput').value;
        const numFaqs = document.getElementById('numFaqs').value;
        const faqLength = document.getElementById('faqLength').value;
        const questionFocusEl = document.getElementById('questionFocus');
        const questionFocus = questionFocusEl ? questionFocusEl.value : 'all';
        
        if (!file && !text.trim()) {
            showToast('Please upload a file or paste text.', 'error');
            return;
        }
        
        startProcessing();
        
        try {
            // 1. Upload
            const formData = new FormData();
            if (file) formData.append('file', file);
            if (text.trim()) formData.append('text', text);
            
            updateProgress('extracting', 'active');
            
            const uploadRes = await fetch(`${API_BASE}/upload`, {
                method: 'POST',
                body: formData
            });
            
            const uploadData = await uploadRes.json();
            
            if (!uploadRes.ok) throw new Error(uploadData.error || 'Upload failed');
            
            updateProgress('extracting', 'done');
            updateProgress('inventory', 'active');
            
            // 2. Generate FAQs
            const statusDiv = document.getElementById('downloadStatus');
            if (statusDiv) {
                statusDiv.style.display = 'block';
                statusDiv.innerHTML = '<i class="bi bi-cpu me-2" style="color: var(--primary-blue);"></i> Initializing local AI inference...';
            }

            const pollInterval = setInterval(async () => {
                try {
                    const progRes = await fetch(`${API_BASE}/progress`);
                    const progData = await progRes.json();
                    if (progData.progress && statusDiv) {
                        const raw = String(progData.progress).trim();
                        // Defensively filter out any HTTP access logs
                        if (!raw.includes('HTTP/') && !raw.includes('127.0.0.1') && !raw.includes(' - - [') && !raw.startsWith('GET') && !raw.startsWith('POST')) {
                            const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);
                            const clean = lines[lines.length - 1];
                            if (clean) {
                                statusDiv.innerHTML = `<i class="bi bi-cpu me-2" style="color: var(--primary-blue);"></i> ${clean}`;
                            }
                        }
                        const p = raw.toLowerCase();
                        if (p.includes('generating') || p.includes('ollama') || p.includes('model') || p.includes('stage b')) {
                            updateProgress('inventory', 'done');
                            updateProgress('generating', 'active');
                        } else if (p.includes('verifying') || p.includes('deduplicat') || p.includes('verif') || p.includes('grounding')) {
                            updateProgress('generating', 'done');
                            updateProgress('verifying', 'active');
                        }
                    }
                } catch (e) {}
            }, 500);
            
            const genRes = await fetch(`${API_BASE}/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    document_id: uploadData.document.id,
                    num_faqs: parseInt(numFaqs),
                    faq_length: faqLength,
                    question_focus: questionFocus
                })
            });
            
            clearInterval(pollInterval);
            
            const genData = await genRes.json();
            if (!genRes.ok) throw new Error(genData.error || 'Generation failed');
            
            updateProgress('generating', 'done');
            updateProgress('verifying', 'done');
            
            setTimeout(() => {
                sessionStorage.setItem('currentDocId', uploadData.document.id);
                sessionStorage.setItem('currentDocName', uploadData.document.filename);
                sessionStorage.setItem('currentGenData', JSON.stringify(genData));
                
                window.location.href = 'results.html';
            }, 800);
            
        } catch (error) {
            console.error(error);
            showToast(error.message, 'error');
            stopProcessing();
        }
    });
}

function startProcessing() {
    dashboardContent.classList.add('d-none');
    processingScreen.classList.remove('d-none');
}

function stopProcessing() {
    dashboardContent.classList.remove('d-none');
    processingScreen.classList.add('d-none');
    // reset icons
    document.querySelectorAll('.processing-step').forEach(step => {
        step.classList.remove('active', 'done');
        step.querySelector('i').className = 'bi bi-circle';
    });
}

function updateProgress(stepId, state) {
    const step = document.getElementById(`step-${stepId}`);
    if (!step) return;
    
    step.classList.remove('active', 'done');
    const icon = step.querySelector('i');
    
    if (state === 'active') {
        step.classList.add('active');
        icon.className = 'spinner-border spinner-border-sm text-primary';
        icon.style.marginRight = '10px';
    } else if (state === 'done') {
        step.classList.add('done');
        icon.className = 'bi bi-check-circle-fill';
    }
}

// Splash Screen Logic
window.addEventListener('load', () => {
    const splashScreen = document.getElementById('splash-screen');
    if (splashScreen) {
        if (!sessionStorage.getItem('splashShown')) {
            sessionStorage.setItem('splashShown', 'true');
            setTimeout(() => {
                splashScreen.classList.add('fade-out');
                setTimeout(() => {
                    splashScreen.remove();
                }, 500);
            }, 1200);
        } else {
            // Already shown in this session, remove instantly
            splashScreen.style.display = 'none';
            splashScreen.remove();
        }
    }
});
