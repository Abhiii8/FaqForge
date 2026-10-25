@echo off
echo ==============================================
echo FAQForge NLP - Setup and Run Script
echo ==============================================

cd /d "%~dp0"

IF NOT EXIST venv (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
)

echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

echo [INFO] Installing required packages...
pip install -r requirements.txt

echo [INFO] Downloading NLTK data...
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('averaged_perceptron_tagger'); nltk.download('wordnet')"

echo [INFO] Downloading spaCy model...
pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1.tar.gz

echo [INFO] Checking for database...
IF NOT EXIST "database" mkdir database

echo ==============================================
echo [INFO] Checking Local AI Engine (Ollama)...
echo ==============================================

set "OLLAMA_CMD=ollama"
where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    )
)

powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Starting Ollama inference engine in background...
    start "" /B "%OLLAMA_CMD%" serve
    ping 127.0.0.1 -n 4 >nul
) else (
    echo [INFO] Ollama engine is already running on port 11434.
)

echo [INFO] Checking qwen2.5:3b model...
"%OLLAMA_CMD%" list | findstr /i "qwen2.5:3b" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Downloading qwen2.5:3b model - one-time setup...
    "%OLLAMA_CMD%" pull qwen2.5:3b
) else (
    echo [INFO] Model qwen2.5:3b is ready.
)

echo ==============================================
echo [INFO] Starting FAQForge NLP web server...
echo [INFO] Access the application at: http://localhost:5000
echo ==============================================
python run.py

pause
