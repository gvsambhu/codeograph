from pathlib import Path
import threading
import json
from codeograph.telemetry.base import TelemetryEmitter
from codeograph.telemetry.telemetry_record import TelemetryRecord

class JsonlEmitter(TelemetryEmitter):
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def emit(self, record: TelemetryRecord) -> None:
        line = json.dumps(record.to_dict(), separators=(",", ":"), ensure_ascii=False)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            self._fh.close()
