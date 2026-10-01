from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    ollama_url: str
    ollama_model: str
    embedding_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        raw_dir = Path(os.getenv("NEUROVAULT_DATA_DIR", "./data")).expanduser()
        data_dir = (BACKEND_DIR / raw_dir).resolve() if not raw_dir.is_absolute() else raw_dir.resolve()
        url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("OLLAMA_URL must be an HTTP URL on 127.0.0.1 or localhost, with no path or credentials")
        return cls(
            data_dir=data_dir,
            ollama_url=url,
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )
