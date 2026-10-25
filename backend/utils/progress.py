import sys
import re

class ProgressCatcher:
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
        self.last_line = "Initializing..."
        self.buffer = ""

    def write(self, s):
        self.original_stderr.write(s)
        self.buffer += s
        
        # tqdm often uses \r to overwrite lines. We split by \r or \n
        # to find the most recent complete line.
        if '\r' in s or '\n' in s:
            # Clean up escape sequences if any (though tqdm might output them)
            # Just take the very last non-empty segment after a \r
            parts = self.buffer.split('\r')
            if len(parts) > 0:
                latest = parts[-1]
                if not latest.strip() and len(parts) > 1:
                    latest = parts[-2]
                
                clean_line = latest.strip()
                if clean_line:
                    # Filter out ANSI escape codes (often used by tqdm)
                    clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', clean_line)
                    self.last_line = clean_line
            
            # Keep buffer small
            if len(self.buffer) > 10000:
                self.buffer = self.buffer[-5000:]

    def flush(self):
        self.original_stderr.flush()

# Singleton instance
progress_catcher = None

def init_catcher():
    global progress_catcher
    if progress_catcher is None:
        progress_catcher = ProgressCatcher(sys.stderr)
        sys.stderr = progress_catcher
