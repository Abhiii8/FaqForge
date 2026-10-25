import os
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, List, Optional, Generator

class OllamaClient:
    """
    Robust local HTTP client for communicating with Ollama inference engine.
    100% offline, private, and local.
    """
    DEFAULT_HOST = "http://127.0.0.1:11434"
    DEFAULT_MODEL = "qwen2.5:3b"

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = (host or os.environ.get("OLLAMA_HOST", self.DEFAULT_HOST)).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.timeout = int(os.environ.get("OLLAMA_TIMEOUT", "120"))

    def check_connection(self) -> Dict[str, Any]:
        """
        Checks whether Ollama service is reachable.
        Returns diagnostic dictionary.
        """
        url = f"{self.host}/api/version"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "running": True,
                    "version": data.get("version", "unknown"),
                    "host": self.host,
                    "active_model": self.model
                }
        except urllib.error.URLError as e:
            return {
                "running": False,
                "version": None,
                "host": self.host,
                "active_model": self.model,
                "error": f"Cannot connect to Ollama at {self.host}. Is Ollama installed and running?",
                "instructions": (
                    "Ollama is not running. Please start Ollama or download it from https://ollama.com. "
                    "On Windows, make sure the Ollama desktop tray application is open."
                )
            }
        except Exception as e:
            return {
                "running": False,
                "version": None,
                "host": self.host,
                "active_model": self.model,
                "error": str(e),
                "instructions": "Ensure Ollama service is running on port 11434."
            }

    def list_models(self) -> List[Dict[str, Any]]:
        """Lists all locally installed models in Ollama."""
        url = f"{self.host}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = []
                for m in data.get("models", []):
                    size_bytes = m.get("size", 0)
                    size_gb = round(size_bytes / (1024 ** 3), 2)
                    models.append({
                        "name": m.get("name"),
                        "model": m.get("model"),
                        "size_bytes": size_bytes,
                        "size_gb": size_gb,
                        "modified_at": m.get("modified_at")
                    })
                return models
        except Exception:
            return []

    def is_model_available(self, model_name: Optional[str] = None) -> bool:
        """Checks if a specific model (or default model) is installed locally."""
        target = (model_name or self.model).lower()
        
        models = self.list_models()
        for m in models:
            m_name = m.get("name", "").lower()
            # Exact match: "qwen2.5:3b" == "qwen2.5:3b"
            if m_name == target:
                return True
            # Subtag match: "qwen2.5:3b" in "qwen2.5:3b-instruct" or "qwen2.5:3b:latest"
            if target in m_name:
                return True
            # Default latest tag: target without tag matches target:latest
            if ":" not in target and m_name.startswith(f"{target}:"):
                return True
        return False

    def pull_model(self, model_name: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Streams model download/pull progress from Ollama.
        Yields status dictionaries with download metrics.
        """
        target = model_name or self.model
        url = f"{self.host}/api/pull"
        payload = json.dumps({"name": target, "stream": True}).encode("utf-8")
        
        req = urllib.request.Request(
            url, 
            data=payload, 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=3600) as resp:
                for line in resp:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        yield chunk
        except Exception as e:
            yield {"status": "error", "error": str(e)}

    def generate(
        self, 
        prompt: str, 
        system: Optional[str] = None, 
        model_name: Optional[str] = None,
        json_format: bool = False,
        temperature: float = 0.2,
        context_window: int = 4096
    ) -> Dict[str, Any]:
        """
        Executes a local inference call to Ollama.
        Supports structured JSON mode and configurable temperature.
        """
        target_model = model_name or self.model
        url = f"{self.host}/api/generate"
        
        payload_data = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": context_window
            }
        }
        if system:
            payload_data["system"] = system
        if json_format:
            payload_data["format"] = "json"
            
        payload = json.dumps(payload_data).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=payload, 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data.get("response", "").strip()
                return {
                    "success": True,
                    "response": response_text,
                    "model": target_model,
                    "total_duration": data.get("total_duration", 0),
                    "eval_count": data.get("eval_count", 0)
                }
        except urllib.error.URLError as e:
            return {
                "success": False,
                "error": f"Ollama connection error: {e.reason}",
                "response": ""
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Ollama generation failed: {str(e)}",
                "response": ""
            }

    def get_embeddings(self, text: str, model_name: Optional[str] = None) -> Optional[List[float]]:
        """Retrieves semantic embeddings from Ollama for similarity checking."""
        target_model = model_name or self.model
        url = f"{self.host}/api/embeddings"
        payload = json.dumps({"model": target_model, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=payload, 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("embedding", None)
        except Exception:
            return None
