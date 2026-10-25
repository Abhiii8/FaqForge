# FAQForge — Advanced Offline AI FAQ Generator

**FAQForge** is an advanced, 100% offline, privacy-first AI application that automatically generates accurate, relevant, non-repetitive, and rigorously verified FAQs from pasted text and multi-page documents (PDF, DOCX, TXT) with exact source citations and document coverage analytics.

---

## Key Features

- **100% Offline AI Inference**: Powered by local **Ollama** (`qwen2.5:3b`) with GPU acceleration and zero external cloud or paid API dependencies.
- **Graceful Neural Fallback**: Seamless fallback to local Hugging Face Transformers (`google/flan-t5-base`).
- **Advanced Document Ingestion (PyMuPDF)**: Full page-by-page extraction, structural heading hierarchy detection, and automatic detection of encrypted, scanned, or empty documents.
- **Intelligent Section-Aware Chunking**: Preserves section boundaries and paragraph integrity with exact page number tracking (`[1, 2]`).
- **Multi-Stage FAQ Generation**: Topic inventory scanning (Definitions, Procedures, Features, Applications) to avoid clustering at document start.
- **Deterministic & Semantic Source Verification**: Morphological root matching with 98%–99% confidence scores, validating numbers, dates, and entities with exact supporting quotes.
- **Semantic Deduplication**: Dual-vector TF-IDF cosine similarity to eliminate redundant semantic variants.
- **Document Coverage Analytics**: Executive summary banner detailing pages analyzed, verification rates, and topic coverage.
- **Scandinavian Minimalist Interface**: Pure monochrome styling, dark mode toggle, collapsible source excerpt accordions, and one-click clipboard copying.
- **Multi-Format Export**: Export verified FAQs to PDF, DOCX, and TXT with metadata citations.

---

## Architecture Overview

```
FAQForge/
├── backend/
│   ├── app.py                     # Flask application factory with database migrations
│   ├── models/
│   │   └── database.py            # SQLite schema (Document, FAQ, Keyword, Entity)
│   ├── nlp/
│   │   ├── chunker.py             # Section & page-aware document chunker
│   │   ├── deduplicator.py        # Dual-vector semantic duplicate detection
│   │   ├── document_processor.py  # PyMuPDF page & heading extractor
│   │   ├── generator.py           # Multi-stage Ollama + Flan-T5 FAQ generator
│   │   ├── ollama_client.py       # Local Ollama HTTP client & streaming
│   │   ├── pipeline.py            # Orchestrator & coverage reporting
│   │   └── verifier.py            # Morphological source verification & quotes
│   ├── routes/
│   │   ├── api.py                 # REST API endpoints (/upload, /generate, /ollama/*)
│   │   └── export.py              # PDF, DOCX, and TXT export routes
│   └── utils/
│       └── progress.py            # Pipeline progress tracking
├── frontend/
│   ├── css/
│   │   └── style.css              # Scandinavian Minimalist styling
│   ├── js/
│   │   └── main.js                # Live status detection & UI interactions
│   ├── index.html                 # Generator dashboard & settings
│   ├── results.html               # Results, coverage banner & verification badges
│   └── history.html               # Historical processed documents
├── run.bat                        # One-click startup (auto-starts Ollama & Flask)
├── run.py                         # Application server entrypoint
└── requirements.txt               # Python package dependencies
```

---

## Quick Start

### 1. One-Click Launch (Recommended)
Double-click `run.bat` in the project root. It will:
1. Verify / start the local Ollama background service (`ollama serve`).
2. Verify that `qwen2.5:3b` is downloaded.
3. Activate the Python virtual environment and install requirements.
4. Launch the web server at [http://localhost:5000](http://localhost:5000).

### 2. Manual Startup
```bash
# 1. Start Ollama with the recommended model
ollama serve
ollama pull qwen2.5:3b

# 2. Activate Python environment & install dependencies
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 3. Run the application
python run.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## License

MIT License. Free for open-source and commercial use.
