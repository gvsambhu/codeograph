"""ManifestAssembler — assembles the terminal 2.0.0 manifest from run-state fragments.

The assembler is the single owner of the manifest-shape rules. The pipeline
collects the artefacts it produces (graph, optionally llm_annotations), the
cache_stats rollup, and the eval/render output pointers, then hands them all
to the assembler for a single build. Strict-on-write Pydantic validation is
the boundary check; the assembler never produces a manifest that violates
the ADR-025 §Invariants.

**Cross-field invariants** (Pydantic encodes per-field, not cross-field, so
the assembler enforces these explicitly):

* ``llm_skipped == True`` ⇒ ``llm_annotations_artefact`` MUST be ``None``.
* ``llm_skipped == False`` ⇒ ``llm_annotations_artefact`` MUST be a
  :class:`GraphArtefact` (the LLM pass has produced the file and its sha).

The assembler raises :class:`ValueError` on a violation rather than letting
the Pydantic ``ValidationError`` mislead the reader about the root cause
(those errors cite a specific missing field, not a state inconsistency).

Agent-noun naming per AGENTS.md §"Python naming conventions".
"""

from __future__ import annotations

from pathlib import Path

from codeograph.manifest.artefact import GraphArtefact
from codeograph.manifest.io import write as manifest_io_write
from codeograph.manifest.models import (
    ArtefactPointer,
    CacheStats,
    CompileChecksPointer,
    Manifest,
    ScorecardPointer,
)

MANIFEST_FILENAME = "manifest.json"


class ManifestAssembler:
    """Assembles the terminal 2.0.0 manifest from run-state fragments.

    Stateless — one instance is reusable across runs. The assembler
    encodes the manifest-shape rules so the run orchestrator can stay
    a thin sequence of *collect → hand-off → write* steps.
    """

    def assemble(
        self,
        *,
        run_id: str,
        codeograph_version: str,
        source_path: str,
        corpus_id: str,
        llm_skipped: bool,
        graph_artefact: GraphArtefact,
        llm_annotations_artefact: GraphArtefact | None = None,
        cache_stats: dict[str, CacheStats] | None = None,
        scorecards: dict[str, ScorecardPointer] | None = None,
        compile_checks: dict[str, CompileChecksPointer] | None = None,
    ) -> Manifest:
        """Build the terminal :class:`Manifest` from run-state fragments.

        Strict-on-write is enforced by Pydantic at construction; a missing
        required field or a present pointer with a non-64-hex sha raises
        :class:`pydantic.ValidationError`. Cross-field invariants
        (``llm_skipped`` consistency with the artefacts dict) are enforced
        here and raise :class:`ValueError` on violation.

        :param run_id:                    Manifest run id (per ADR-022 Fork 3
                                           format ``YYYY-MM-DDTHH-MM-SSZ-<6hex>``).
        :param codeograph_version:        The producing tool's version
                                           (e.g. ``"0.1.0"`` from
                                           :mod:`codeograph.__init__`).
        :param source_path:               Absolute path to the input corpus
                                           (POSIX-form on disk).
        :param corpus_id:                 Stable identifier for this corpus
                                           (the root directory name by
                                           default).
        :param llm_skipped:               ``True`` for ``--ast-only`` runs,
                                           ``False`` for full runs. The
                                           assembler asserts the consistency
                                           of this flag with
                                           ``llm_annotations_artefact``.
        :param graph_artefact:            The deterministic graph
                                           (always present; required).
        :param llm_annotations_artefact:  The LLM-annotated output
                                           (required when ``llm_skipped``
                                           is ``False``; MUST be ``None``
                                           when ``llm_skipped`` is
                                           ``True``).
        :param cache_stats:               Per-pass cache rollup
                                           (optional; ``None`` for
                                           ``--ast-only`` and for full
                                           runs that haven't aggregated
                                           yet).
        :param scorecards:                Eval scorecard pointers, keyed
                                           by kind (optional; ``None`` if
                                           eval did not run).
        :param compile_checks:            Render compile-check sidecar
                                           pointers, keyed by target
                                           (optional; ``None`` if render
                                           did not run).
        :returns:                         A :class:`Manifest` ready for
                                           strict-on-write serialisation.
        :raises ValueError:               If ``llm_skipped`` is inconsistent
                                           with ``llm_annotations_artefact``.
        :raises pydantic.ValidationError: If a required field is missing or
                                           a pointer's ``sha256`` is not
                                           64-hex.
        """
        # --- Cross-field invariant enforcement ----------------------------
        if llm_skipped and llm_annotations_artefact is not None:
            raise ValueError(
                "llm_skipped=True but llm_annotations_artefact is set "
                f"({llm_annotations_artefact.path}). Per ADR-025 Fork 3, "
                "an --ast-only run omits the llm_annotations pointer "
                "entirely; the LLM-annotation file must not exist on disk "
                "for the skipped state."
            )
        if not llm_skipped and llm_annotations_artefact is None:
            raise ValueError(
                "llm_skipped=False but llm_annotations_artefact is None. "
                "Per ADR-025 §Invariants, a full run MUST have an "
                "llm_annotations ArtefactPointer (present iff llm_skipped "
                "is false)."
            )

        # --- Build the artefacts dict (always has graph; conditionally
        #     has llm_annotations per the invariant above) -----------------
        artefacts: dict[str, ArtefactPointer] = {
            "graph": ArtefactPointer(
                path=graph_artefact.path.name,
                schema_version=graph_artefact.schema_version,
                sha256=graph_artefact.sha256,
            ),
        }
        if not llm_skipped and llm_annotations_artefact is not None:
            artefacts["llm_annotations"] = ArtefactPointer(
                path=llm_annotations_artefact.path.name,
                schema_version=llm_annotations_artefact.schema_version,
                sha256=llm_annotations_artefact.sha256,
            )

        return Manifest(
            schema_version="2.0.0",
            codeograph_version=codeograph_version,
            source_path=source_path,
            corpus_id=corpus_id,
            run_id=run_id,
            llm_skipped=llm_skipped,
            cache_stats=cache_stats,
            artefacts=artefacts,
            scorecards=scorecards,
            compile_checks=compile_checks,
        )

    def write_to(self, manifest: Manifest, out_dir: Path) -> Path:
        """Write the terminal manifest to ``out_dir/manifest.json``.

        Uses :func:`codeograph.manifest.io.write` for strict-on-write
        serialisation. Creates the parent directory if it does not exist.

        :param manifest: The terminal :class:`Manifest` to write.
        :param out_dir:  Directory to write ``manifest.json`` into.
        :returns:        The path the manifest was written to.
        """
        path = out_dir / MANIFEST_FILENAME
        manifest_io_write(manifest, path)
        return path


__all__ = ["MANIFEST_FILENAME", "ManifestAssembler"]
