"""Render orchestration service (ADR-008 Fork 6, SRP-02 extraction).

``RenderPipeline`` owns everything between "artefacts are loaded" and
"output is on disk and the manifest pointer is updated":

  LLM-stack build → renderer.render → compile-checks sidecar →
  collapse-warning analysis → file flush → manifest pointer patch.

``render_cli`` (``cli/render.py``) is the thin CLI adapter that loads
artefacts, resolves the output directory, and delegates here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeograph.config.settings import Settings
    from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph

__all__ = ["RenderPipeline", "RenderResult"]


@dataclass
class RenderResult:
    """Outcome of a completed render run."""

    written: int
    warnings: list[str] = field(default_factory=list)
    run_id: str = ""
    sidecar_path: Path | None = None


class RenderPipeline:
    """Orchestrates a single ``codeograph render`` run.

    Separated from the Click handler so the render logic is independently
    testable: callers pass in-memory domain objects; the pipeline owns
    LLM-stack construction, rendering, sidecar creation, and manifest patching.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run(
        self,
        graph: CodeographKnowledgeGraph,
        annotations: dict[str, object],
        raw_config: dict[str, object],
        target: str,
        from_path: Path,
        out_path: Path,
    ) -> RenderResult:
        """Execute the render pipeline and return a :class:`RenderResult`.

        *from_path* is the source run-output directory (read for the manifest
        pointer patch).  *out_path* is the destination render directory (must
        already exist; ``prepare_output_directory`` is the caller's job).
        """
        from codeograph import __version__ as _codeograph_version
        from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend
        from codeograph.llm.factory import build_default_stack
        from codeograph.llm.middleware.retry_policy import RetryPolicy
        from codeograph.llm.models import CallContext, Purpose
        from codeograph.llm.prompts.loader import PromptLoader
        from codeograph.llm.resolver import LlmProviderResolver
        from codeograph.manifest.io import read as manifest_io_read
        from codeograph.manifest.io import write as manifest_io_write
        from codeograph.manifest.models import CompileChecksPointer
        from codeograph.manifest.run_id import generate_run_id
        from codeograph.renderers import RendererRegistry
        from codeograph.telemetry.emitter import JsonlEmitter

        settings = self._settings

        # --- build LLM stack ------------------------------------------------
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_backend = SQLiteCacheBackend(settings.cache_dir / "cache.db")

        telemetry_dir = settings.cache_dir / "telemetry"
        telemetry_dir.mkdir(parents=True, exist_ok=True)

        run_id = generate_run_id()
        emitter_path = telemetry_dir / f"render-{target}-{run_id}.jsonl"
        emitter = JsonlEmitter(emitter_path)

        base_provider = LlmProviderResolver(settings).resolve()
        retry_policy = RetryPolicy()

        prompt_loader = PromptLoader(Path(__file__).parent.parent / "prompts")

        # Resolve the render prompt's content_hash_pin from the renderer's own
        # prompt directory so the cache key is tied to the actual prompt body
        # (ADR-014 / ADR-015).
        _ts_render_prompts = PromptLoader(Path(__file__).parent.parent / "renderers" / "typescript_nestjs" / "prompts")
        _render_prompt = _ts_render_prompts.get("render_file", version="v1")
        _render_prompt_hash = _render_prompt.metadata.content_hash_pin

        render_ctx = CallContext(
            run_id=run_id,
            pipeline_name="render",
            pipeline_run_id=run_id,
            purpose=Purpose.RENDER,
            prompt_id="render_file",
            prompt_version="v1",
            prompt_content_hash=_render_prompt_hash,
            corpus_id=from_path.name,
            provider_name=settings.resolved_provider_label,
        )
        provider = build_default_stack(base_provider, retry_policy, cache_backend, emitter, render_ctx)

        # --- instantiate renderer and render --------------------------------
        try:
            renderer = RendererRegistry.build(
                target=target,
                raw_config=raw_config,
                provider=provider,
                prompt_loader=prompt_loader,
                concurrency=settings.llm_concurrency,
            )
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

        file_map = renderer.render(graph, annotations)

        # --- compile-checks sidecar (ADR-017 Fork 8) ------------------------
        _compile_checks = renderer.compile_checks()
        _sidecar_rel_path: PurePosixPath | None = None
        _sidecar_sha256: str | None = None

        if _compile_checks:
            _sidecar_dict = {
                "schema_version": "1.0.0",
                "target": target,
                "renderer_version": _codeograph_version,
                "checks": [
                    {
                        "name": c.name,
                        "cmd": list(c.cmd),
                        "workdir": str(c.workdir),
                        "required_tools": list(c.required_tools),
                        "pass_on_exit_codes": list(c.pass_on_exit_codes),
                    }
                    for c in _compile_checks
                ],
            }
            _sidecar_bytes = json.dumps(_sidecar_dict, indent=2).encode("utf-8")
            _sidecar_rel_path = PurePosixPath(f"evals/compile-checks.{target}.json")
            _sidecar_sha256 = hashlib.sha256(_sidecar_bytes).hexdigest()
            file_map[_sidecar_rel_path] = _sidecar_bytes

        # --- PackagePrefixGrouping collapse warning (ADR-009 / Issue #7) ----
        warnings: list[str] = []
        if not raw_config.get("domain_mapping"):
            _domain_dirs = {p.parts[1] for p in file_map if len(p.parts) >= 3 and p.parts[0] == "src"}
            _src_ts_files = [
                p
                for p in file_map
                if p.parts[0] == "src" and p.name.endswith(".ts") and not p.name.endswith(".module.ts")
            ]
            if len(_domain_dirs) == 1 and len(_src_ts_files) > 5:
                warnings.append(
                    "WARNING: PackagePrefixGrouping produced only 1 domain group from "
                    f"{len(_src_ts_files)} rendered classes. "
                    "This usually means the longest common package prefix is too shallow "
                    "(mixed-vendor codebase). "
                    "Consider using ManualMappingGrouping via "
                    "'[render.typescript.domain_mapping]' in your config. "
                    "See ADR-009 Amendments for details."
                )

        # --- flush rendered files + sidecar to disk -------------------------
        out_path.mkdir(parents=True, exist_ok=True)
        written = 0
        for rel_path, content in file_map.items():
            dest = out_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            written += 1

        # --- manifest pointer patch (ADR-017 Fork 8, ADR-025 write-protocol) -
        # Sidecar is on disk before pointer is written (per ADR-017 Fork 8).
        sidecar_abs_path: Path | None = None
        if _sidecar_rel_path is not None and _sidecar_sha256 is not None:
            manifest_path = from_path / "manifest.json"
            if manifest_path.exists():
                manifest = manifest_io_read(manifest_path)
                if manifest.compile_checks is None:
                    manifest.compile_checks = {}
                manifest.compile_checks[target] = CompileChecksPointer(
                    path=str(_sidecar_rel_path),
                    sha256=_sidecar_sha256,
                )
                manifest_io_write(manifest, manifest_path)
            sidecar_abs_path = out_path / _sidecar_rel_path

        emitter.close()

        return RenderResult(
            written=written,
            warnings=warnings,
            run_id=run_id,
            sidecar_path=sidecar_abs_path,
        )
