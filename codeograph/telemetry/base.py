from abc import ABC, abstractmethod
from codeograph.telemetry.telemetry_record import TelemetryRecord

class TelemetryEmitter(ABC):
    @abstractmethod
    def emit(self, record: TelemetryRecord) -> None: ...
    @abstractmethod
    def close(self) -> None: ...
