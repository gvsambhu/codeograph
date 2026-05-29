# Re-export shim — ADR-015 specifies codeograph/telemetry/emitter.py as the
# canonical import path for JsonlEmitter; the implementation lives in
# jsonl_emitter.py (the two names are intentional: emitter.py is the public
# API, jsonl_emitter.py is the concrete class module).
from codeograph.telemetry.jsonl_emitter import JsonlEmitter

__all__ = ["JsonlEmitter"]
