import sys
import re

# Blacklist of log patterns that should NEVER be exposed as pipeline progress
SERVER_LOG_PATTERNS = [
    ' - - [',
    'HTTP/1.',
    'GET /',
    'POST /',
    'PUT /',
    'DELETE /',
    'HEAD /',
    'OPTIONS /',
    '127.0.0.1',
    'localhost',
    'Debugger',
    'Restarting with',
    'Running on',
    'Press CTRL+C',
    '* Debugger',
    'FutureWarning',
    'UserWarning',
    'DeprecationWarning'
]

class ProgressCatcher:
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
        self.last_line = "Initializing document pipeline..."
        self.buffer = ""

    def set(self, msg: str):
        """Explicitly set user-facing progress message."""
        if msg and isinstance(msg, str):
            clean = msg.strip()
            if clean:
                self.last_line = clean

    def write(self, s):
        # Always output to actual console stderr for debugging
        self.original_stderr.write(s)
        
        # Completely skip server access logs or warnings
        for pattern in SERVER_LOG_PATTERNS:
            if pattern in s:
                return

        self.buffer += s
        
        # Split on newline or carriage return to find the latest clean progress message
        if '\r' in s or '\n' in s:
            parts = re.split(r'[\r\n]+', self.buffer)
            for part in reversed(parts):
                clean_line = part.strip()
                if clean_line:
                    # Strip ANSI escape codes
                    clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', clean_line).strip()
                    # Verify it's not a server log
                    if clean_line and not any(p in clean_line for p in SERVER_LOG_PATTERNS):
                        self.last_line = clean_line
                        break
            
            # Keep buffer bounded
            if len(self.buffer) > 2000:
                self.buffer = self.buffer[-500:]

    def flush(self):
        self.original_stderr.flush()

# Singleton instance
progress_catcher = None

def init_catcher():
    global progress_catcher
    if progress_catcher is None:
        progress_catcher = ProgressCatcher(sys.stderr)
        sys.stderr = progress_catcher
