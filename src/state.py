from __future__ import annotations
import json
from pathlib import Path

class StateStore:
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {"products": {}, "discovered": {}, "last_cycle": None, "last_error": ""}
        self.load()

    def load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)
