---
status: proposed
date: 2026-11-01
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-032 — Evaluation Check Semantics

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0, `main` at `420f2b5` (2026-11-01). ADR text is
cited as it stands at that commit.

ADR-017 Fork 3 locked the seven graph-quality check definitions *"exactly"*, and Fork 4 locked the three
code-quality slots. Each definition was written as a formula. **Four of the formulas cannot measure what
their check's name says**, and one code-quality slot had no designed input:

| Check | ADR-017 definition | Why it cannot measure what its name says |
|---|---|---|
| `structural_completeness` | `(class+method+field nodes emitted) / (declarations in source)` | The parser is the only source of "declarations in source" (ADR-003), and the parser is the component the check polices. A declaration the parser missed is absent from both sides, so the ratio stays 1.0 |
| `relationship_correctness` | `resolved_edges / (total_edges − unresolved_call_edges)` | Every reference that fails to resolve is emitted as unresolved (FR-40) and so leaves the denominator; the ratio falls below 1.0 only when an edge endpoint is missing, which `internal_consistency` already counts |
| `internal_consistency` | five invariants, (a)–(e) | Invariant (d), *"every ADR-009 domain non-empty"*, asserts a rendering-stage property in a graph-stage check — domains do not exist in the graph (ADR-009, ADR-006). Invariant (e) requires every unresolved call to carry a target FQCN, which ADR-003 says an unresolved call does not have. And the cross-file rule ADR-006 assigned to this check — every annotation key resolves to a class node — is not among the five |
| `reproducibility` | re-run `--ast-only` three times on the recorded source path; compare the three hashes | The scored graph is never an operand. A graph that differs from its enrichment-off twin (FR-34 AC-3) passes, because the check compares three fresh runs with each other; and a source changed since the run is certified as if it were the old one |
| `coverage` (code slot 2) | feature coverage over ADR-010 Fork 9's audit | The audit data is produced while rendering and nothing carried it to evaluation, so the check never ran. Its empty-input skip reason (*"no translatable features in corpus"*) states something about the corpus when the truth is that the input is missing |

Two further gaps: no check re-validates the annotations file, although FR-7b AC-2 requires the
scorecard to re-check *"every emitted graph and annotation file"*; and the requirements include FR-41,
a human-checked expectation of what a graph should contain — the oracle a correctness check needs and
ADR-017 never had.

**The output layout supplies inputs that did not exist when ADR-017 was written.** ADR-029 places a
render-owned audit file at `evals/render-audit.<target>.json`, indexed from the manifest; the
amendment to ADR-010 that accompanies the output-layout ADRs fixes its contents (the selection audit,
refused classes with the refusing policy, the stub sites, the active policies).

**This ADR supersedes ADR-017 Fork 3's definitions of `structural_completeness`,
`relationship_correctness`, `internal_consistency` and `reproducibility`, and Fork 4's definition of the
`coverage` slot's inputs and arithmetic, and adds one graph check.** Everything else in ADR-017 stands —
the scorecard schema and storage, the threshold model, the invocation surface, the compile-check policy,
multi-corpus reporting, and the definitions of `schema_validity`, `semantic_accuracy` and
`golden_graph_agreement`.

## Decision Drivers

* **Measure what the name says** — a check whose value cannot move, or cannot see the failure it is named
  for, is worse than no check: it reports green on the defect.
* **No silent failures** — when a check's input is missing it skips with a reason that says so, never with
  a reason that claims something about the corpus (FR-7 AC-4).
* **Determinism / determinism boundary clarity** — the graph is a function of the corpus and the tool
  (FR-34); the check that guards that property must read the graph it scores, and must tell a defect from a
  change of environment (NFR-6 AC-4).
* **One oracle for correctness** — the checks that claim correctness rest on one human-checked artefact
  (FR-41), not on the extractor being judged.
* **Schema discipline** — every change to the scorecard is additive within its major version (NFR-7 AC-3).

## Considered Options

### Fork 1 — The ground truth for `structural_completeness`

* **(a) FR-41's confirmed expectation; skip where none exists. ✅**
* (b) A second, independent lightweight declaration counter, accepted as approximate.
* (c) Redefine the check to what the graph alone can show, and rename it.
* (d) Reserve the check as a deferred skip until v1.1.

### Fork 2 — What `relationship_correctness` measures

* (a) The call-resolution rate, renamed to say so.
* **(b) Agreement with FR-41's confirmed expectation; the resolution rate in the details. ✅**
* (c) Retire it into `internal_consistency`'s referential-integrity rules.

### Fork 3 — The `internal_consistency` rule set

* (a) The five invariants as locked.
* **(b) Five rules: drop invariant (d); restate invariant (e) as origin FQCN plus target identifier; add
  the annotation-key join. ✅**
* (c) Move invariant (d) to the target scorecard; restate (e).
* (d) Drop both (d) and (e).

### Fork 4 — What `reproducibility` compares

* **(a) One `--ast-only` re-run, pinned to the run's record, against the scored graph's hash; drift in the
  source or the environment skips. ✅**
* (b) Keep the three-way self-consistency test under a new name, and add a separate check for FR-34 AC-3.
* (c) Keep the definition; document what it does and does not show.

### Fork 5 — The `coverage` slot's inputs

* **(a) Read the render audit; encountered features from the selected classes' graph annotations. ✅**
* (b) Defer the slot to v1.1 with a reserved skip.
* (c) Redefine as render coverage (classes rendered / classes selected).

### Fork 6 — Re-validating the annotations file

* (a) Extend `schema_validity` to cover both files.
* **(b) A new graph check, `annotations_schema_validity`. ✅**
* (c) Rely on write-time validation alone.

## Decision Outcome

### Fork 1 — `structural_completeness` against FR-41's expectation: (a)

* **Value** — over the expectation's **confirmed** declaration entries only (FR-41 AC-3):
  `|confirmed expected declarations present in the graph| / |confirmed expected declarations|`. A
  declaration matches by kind and fully qualified identity.
* **Threshold** — `MinRatioThreshold(pass_at_or_above=1.0)`, sharp. A confirmed declaration the graph
  lacks is an extraction miss by definition; no published benchmark is needed for "everything a person
  confirmed is present". **A sharp ratio below its bar derives to `fail`**, never `skip` (see
  *Constraint flagged for ADR-017*). `details.missing` lists the misses.
* **No expectation for the corpus** → `result: "skip"`, `details.skip_reason: "no_expectation"`. Until
  FR-41's expectation exists (v1.1), every corpus takes this skip: a skip is the truthful state for a
  number that could not move.
* The check's name and FR-7a's vocabulary are unchanged.

### Fork 2 — `relationship_correctness` against FR-41's expectation: (b)

* **Scope** — the relationships whose origin is a confirmed expectation entry whose outgoing
  relationships the expectation marks complete (see *Constraint flagged for the FR-41 expectation ADR*).
  An origin whose relationships are only partly listed is outside the scope, so a true edge the
  expectation has not yet listed is never counted as unexpected.
* **Value** — `|expected ∩ emitted| / |expected ∪ emitted|` over that scope: 1.0 only when every expected
  relationship is emitted and every emitted one is expected, so misses and spurious edges both lower it.
  `details.missing` and `details.unexpected` list each.
* **Threshold** — `MinRatioThreshold(pass_at_or_above=1.0)`, sharp, deriving to `fail` below the bar, for
  the same reason as Fork 1.
* **No expectation** → skip with `no_expectation`.
* **Always reported, never scored:** `details.call_resolution_rate =
  resolved calls / (resolved + unresolved calls)` — informative on every corpus, including those without
  an expectation, with no threshold because none can be cited — and `details.resolution_mode`, the run's
  resolution mode (ADR-033), since that mode decides which third-party calls can resolve.

### Fork 3 — Five `internal_consistency` rules: (b)

The value is the count of violations across:
1. node id uniqueness within kind;
2. every class references a valid package;
3. every method's parent class exists;
4. every unresolved call carries its origin FQCN and its target identifier (ADR-003 §5; FR-40 AC-1);
5. every key in the annotations file resolves to a class node in the graph — run only when the run has
   annotations; a class node with no annotation is not a violation (ADR-006, 2026-06-17 item 4; FR-34
   AC-4).

The scorecard discloses the rule set it enforced: `details.rules_enforced` (5, or 4 when there are no
annotations), with the rule names. When rule 5 runs, the graph scorecard's input fingerprint includes the
annotations' SHA-256 (the output-layout amendment to ADR-017). The dropped invariant guarded a case the
default domain grouping cannot produce; its one real form — a manual domain-mapping entry that matches no
class — is a configuration error, caught when `render` starts (FR-38 AC-2; see *Constraint flagged for
ADR-009*).

### Fork 4 — `reproducibility` reads the scored graph: (a)

**At run time** the manifest records:
* a **corpus fingerprint** — over every file Pass 0 reads to build the graph: the corpus's source files,
  and the build files and ignore-rule files that discovery and module enumeration read (FR-1 AC-3, FR-30
  AC-1, AC-2). Its serialisation is fixed: one line per file — the POSIX corpus-relative path, a tab, the
  lowercase hex SHA-256 of the file's bytes, LF — with lines sorted by path in byte order, encoded as
  UTF-8; the fingerprint is the SHA-256 of that text. Content, not location, so the same corpus at two
  paths fingerprints identically;
* the **execution envelope** the run observed — the JDK's version and vendor, or that no JDK was
  available, and the operating-system family — beside the tool version the manifest already holds;
* the **Pass-0 settings** that change the graph, and the resolution mode with its classpath record
  (ADR-033).

**At evaluation**, each step that cannot be satisfied skips with its reason — the check never certifies,
or fails, a comparison it was not given:
1. The graph as read must have the SHA-256 the manifest records for it. Different →
   `graph_modified_since_run`.
2. The running tool's version must equal the recorded one. Different → `tool_version_changed`.
3. The current envelope must equal the recorded one. Different → `envelope_changed`.
4. Acquire the source from the manifest's recorded `source_path` — the source as given (a local path, a
   URL or an archive), per the output-layout amendment to ADR-025. Unavailable → `source_path_unavailable`.
5. Recompute the corpus fingerprint. Different → `source_changed`.
6. Resolution follows the **run's record, never ambient configuration**. A corpus-only run is re-run
   corpus-only even when a classpath setting is present. A classpath run needs its classpath supplied
   again (ADR-033 Fork 1), and the record built from it must have the recorded summary hash. Missing or
   different → `resolution_environment_changed`.
7. If the scored run recorded a transient extraction degradation (ADR-033) →
   `transient_degradation_in_scored_run`: the graph is already known not to be reproducible, for a
   recorded environmental reason.
8. Run Pass 0 once with `--ast-only`, the recorded resolution mode and the recorded Pass-0 settings, into a
   temporary location; compare its canonical-form SHA-256 with the scored graph's. Equal → pass;
   different → fail, with both hashes in the details.

This asserts FR-34 AC-3 and NFR-6 directly — an enrichment-on graph that differs from its enrichment-off
twin fails — while drift in the source, the tool or the envelope stops the comparison instead of being
reported as a difference (NFR-6 AC-4). One Pass-0 run replaces three. `--skip-check reproducibility` stays
the opt-out.

### Fork 5 — `coverage` reads the render audit: (a)

* **Inputs** — `evals/render-audit.<target>.json` (ADR-029), located and verified through its manifest
  entry and SHA-256 (ADR-025), with the contents fixed by the output-layout amendment to ADR-010; and
  the graph.
* **The class set** is ADR-009's selection **before** refusal: refused and failed classes are part of it,
  so their features count against the score.
* **Encountered features** — the annotations captured on those classes' graph nodes (FR-32 AC-1),
  mapped to ADR-010 Fork 9's matrix rows. ADR-017's *"framework patterns"* term is dropped: nothing
  produced it.
* **Arithmetic:** translatable = encountered ∩ the matrix's v1 rows; emitted = translatable − features
  dropped under `stub_todo` − features in refused classes − features in classes whose render call failed;
  value = |emitted| / |translatable|. A placeholder translates none of its class's features (ADR-034).
  The 95% / 85% band stands, and becomes calibratable against the committed examples.
* **A missing or corrupt audit** (absent, or its SHA-256 differs from the manifest's) → skip,
  `render_audit_missing_or_corrupt`. `no_v1_translatable_features_in_corpus` is kept only for its literal
  meaning: the audit was read and the translatable set is empty.

### Fork 6 — `annotations_schema_validity`: (b)

* A new graph check: `llm-annotations.json` validates against its published schema (FR-7b AC-2).
  `BooleanThreshold(expected=True)`; deterministic.
* A run without annotations (`--ast-only`) → skip, `no_annotations`.
* **No model provenance is recorded** (`model_version`, `prompt_id` and `provider` null). FR-18 AC-1 asks
  for provenance so that a score that moves can be attributed to the tool or to the model; whether a file
  validates does not move with the model, because write-time validation (FR-7b AC-1) makes a failure a
  writer defect.
* The check reads the annotations, so the graph scorecard's input fingerprint includes their SHA-256
  (the output-layout amendment to ADR-017 records each scorecard's input fingerprints).
* Adding a check is an additive scorecard change (ADR-017 Fork 3).

### Constraints flagged for other ADRs

#### Constraint flagged for the FR-41 expectation ADR
To be written when FR-41 is scheduled. The expectation holds declarations and relationships, each marked
confirmed or not, keyed so Fork 1 matches by kind and fully qualified identity and Fork 2 by origin, kind
and target. It also decides: a per-origin mark that the origin's outgoing relationships are listed
completely (Fork 2's scope); how an expected relationship into a library matches an emission that is
unresolved under a corpus-only run (ADR-033); and how a difference classified as an intentional change
(FR-41 AC-4) is treated against the sharp thresholds of Forks 1 and 2.

#### Constraint flagged for ADR-025
The manifest records the corpus fingerprint, the execution envelope and the graph-affecting Pass-0
settings (Fork 4) — additive.

#### Constraint flagged for ADR-033
Fork 4 reads its resolution record, its classpath summary hash and its transient-degradation flag, and
re-runs in the recorded mode.

#### Constraint flagged for ADR-009
A manual domain mapping whose entry matches no class is rejected when `render` starts, after the graph is
loaded and before any render work (Fork 3).

#### Constraint flagged for ADR-006
Its 2026-06-17 item 4 constraint — the annotation-key join, checked by the internal-consistency
evaluation — is discharged by Fork 3's rule 5.

#### Constraint flagged for ADR-017
On acceptance, Fork 3's four superseded definitions and Fork 4's coverage definition carry a *superseded
by ADR-032* note; the skip-reason taxonomy gains `no_expectation`, `graph_modified_since_run`,
`tool_version_changed`, `envelope_changed`, `source_changed`, `resolution_environment_changed`,
`transient_degradation_in_scored_run`, `render_audit_missing_or_corrupt` and `no_annotations`; and Fork 2's
derivation table states that a sharp `MinRatioThreshold` below its bar derives to `fail`.

#### Constraint flagged for ADR-021
The determinism contract absorbs or cites Fork 4's envelope record and its skip-on-drift rule.

#### Constraint flagged for ADR-026
The version consequences of this ADR, ADR-033, ADR-034 and the amendments that accompany them, applied
when the code ships (ADR-026: the bump is decided at release) — **one bump per artefact per release,
merged with the output-layout cluster's where both ship in the same release**:
* **the graph schema** takes its next major (`signatures_only` leaves `extraction_mode`; `name_only`
  joins it — ADR-006);
* **the annotations schema** takes its next major (`annotation_mode` and `call_status` replace
  `extraction_mode`; the record gains `provider` and the reduction's reason and estimate — ADR-006);
* **the manifest schema** takes its next minor (corpus fingerprint, envelope, Pass-0 settings,
  resolution, extraction counts, enrichment counts, two artefact entries — ADR-025);
* **the scorecard schema** takes its next minor (`annotations_schema_validity`, `provider` in
  provenance, new skip reasons — ADR-017);
* **the render audit** takes its next minor (render failures and placeholders — ADR-010, ADR-034);
* **the extraction report and the classpath record** start at `1.0.0` (ADR-033);
* **the tool** takes a minor in `0.x` (the classpath and parser-timeout settings).

## Consequences

* Good, because every graph check either measures what its name says or skips with a reason that says why.
* Good, because `reproducibility` fails on the defect it exists to catch — an LLM-enabled graph that
  differs from its enrichment-off twin — and skips, rather than fails, when the source, the tool or the
  environment has changed since the run.
* Good, because the two correctness checks share one human-checked oracle, so a fact the extractor never
  produced can finally register as missing.
* Good, because `coverage` produces a value that counts refused and failed classes against it, and its
  band can be calibrated.
* Good, because the annotation-key join ADR-006 assigned to this check is finally enforced.
* Bad, because until FR-41's expectation exists (v1.1), `structural_completeness` and
  `relationship_correctness` skip on every corpus — the graph scorecard reports fewer passes than before,
  though each earlier pass carried no information. User-visible; it reaches the README in the shipping PR.
* Bad, because `reproducibility` must re-acquire the source: a git source is cloned again, and a source
  that has moved on since the run skips rather than scores.
* Bad, because `reproducibility` compares only like with like: a graph produced by another tool version,
  JDK or operating system skips, so a scorecard taken elsewhere says less than one taken where the run
  happened.
* Bad, because the run manifest gains a corpus fingerprint and an envelope record, which cost one hash per
  input file at run time.
* Neutral, because the graph scorecard gains a check and new skip reasons — an additive schema change.

## Confirmation

1. On a corpus with no expectation, `structural_completeness` and `relationship_correctness` record
   `result: "skip"` with `details.skip_reason == "no_expectation"`; `relationship_correctness` still
   reports `details.call_resolution_rate` and `details.resolution_mode` (integration test).
2. On a fixture expectation with one confirmed method the graph lacks, `structural_completeness` records
   `result: "fail"` — not `skip` — with that method in `details.missing`, and the scorecard's `overall` is
   `fail` (unit test).
3. On a fixture expectation whose origin is marked complete, with one confirmed relationship missing and
   one unexpected relationship emitted, `relationship_correctness` fails with value `n/(n+2)` for `n`
   matched relationships, listing both; an extra emitted relationship from an origin not marked complete
   does not change the value (unit tests with hand-worked expected values).
4. `internal_consistency` reports `details.rules_enforced == 5` on an LLM-enabled run and `4` on an
   `--ast-only` run; an unresolved call with an origin FQCN and a target identifier but no target FQCN is
   not a violation; an annotations key with no matching class node is one violation; a class node with no
   annotation is not (unit tests).
5. A fixture run whose recorded graph differs from an `--ast-only` re-run of the same corpus (a Pass-0
   stage injected with a non-deterministic value) makes `reproducibility` fail with both hashes in the
   details; editing the graph file after the run makes it skip with `graph_modified_since_run`
   (integration tests).
6. Changing one corpus file, or the corpus's build file, after the run makes `reproducibility` skip with
   `source_changed` (integration test).
7. A manifest whose recorded tool version, or JDK version, differs from the evaluating environment makes
   `reproducibility` skip with `tool_version_changed` or `envelope_changed` (unit tests).
8. Evaluating a corpus-only run with a classpath setting present re-runs corpus-only and passes; a
   classpath run evaluated without its classpath skips with `resolution_environment_changed` (integration
   tests).
9. A scored run whose manifest records a transient extraction degradation makes `reproducibility` skip
   with `transient_degradation_in_scored_run` (unit test).
10. With a render audit present and verified, `coverage` records a numeric value; a render in which one
    selected class's call failed scores below 1.0, as does one with a refused class; with the audit
    deleted, or one byte changed, it skips with `render_audit_missing_or_corrupt` (integration tests).
11. An annotations file that violates its schema fails `annotations_schema_validity`, with null model
    provenance; an `--ast-only` run skips it with `no_annotations` (integration test).
12. The corpus fingerprint of a fixture corpus equals a hand-computed value over its listed files, and is
    the same from two different directories (unit test).
13. The committed scorecard JSON Schema regenerates cleanly at its new minor version (CI freshness gate).
14. A manual domain mapping with an entry matching no class makes `render` fail at startup with a message
    naming the entry, before any render work (unit test).

## Pros and Cons of the Considered Options

### Fork 1 — Ground truth for `structural_completeness`

**(a) FR-41's confirmed expectation. ✅ Chosen.**
* Good, because the oracle is independent of the extractor, so a missed declaration registers.
* Good, because it is the oracle the requirements already specify (FR-41), shared with Fork 2.
* Bad, because the check skips on every corpus until an expectation is written.

**(b) A second lightweight counter.**
* Good, because it yields a number on every corpus.
* Good, because it needs no human authoring.
* Bad, because it checks one heuristic against another; where both miss the same declaration, nothing
  registers.

**(c) Redefine and rename.**
* Good, because a computable, honest number exists on every corpus (e.g. the share of files extracted at
  full fidelity).
* Good, because it needs no new artefact.
* Bad, because it measures something other than completeness, and FR-7a names the check.

**(d) Deferred skip.**
* Good, because it is honest and costs nothing.
* Good, because it leaves the design open.
* Bad, because it names no oracle, so FR-41's build has no consumer specified.

### Fork 2 — What `relationship_correctness` measures

**(a) Call-resolution rate.**
* Good, because it is computable on every corpus.
* Good, because it moves when resolution degrades.
* Bad, because no published threshold exists; a resolution rate is not correctness, and FR-7a's name
  would change.

**(b) Agreement with FR-41's expectation. ✅ Chosen.**
* Good, because it detects both missing and spurious relationships.
* Good, because it shares Fork 1's oracle, and keeps the resolution rate visible in the details.
* Bad, because it skips until an expectation exists, and scores only origins whose relationships are
  listed completely.

**(c) Retire into `internal_consistency`.**
* Good, because it removes a check that cannot move.
* Good, because referential integrity is already counted there.
* Bad, because FR-7a loses a named check, and correctness of relationships goes unmeasured.

### Fork 3 — The `internal_consistency` rule set

**(a) Five invariants as locked.**
* Good, because nothing changes.
* Good, because every invariant is a plausible property.
* Bad, because invariant (d) is unanswerable at graph time, invariant (e) contradicts ADR-003, and the
  annotation-key join ADR-006 assigned to the check is missing.

**(b) Drop (d), restate (e), add the annotation-key join. ✅ Chosen.**
* Good, because every rule is checkable from the run's artefacts and consistent with ADR-003, ADR-006 and
  FR-40.
* Good, because the dropped rule's one real case moves to a startup configuration check.
* Bad, because the rule count depends on whether the run has annotations, so the scorecard must disclose
  it.

**(c) Move (d) to the target scorecard; restate (e).**
* Good, because domain data exists there (the render audit).
* Good, because no rule is lost.
* Bad, because the default grouping cannot produce an empty domain, so the moved rule guards nothing.

**(d) Drop both.**
* Good, because it is the smallest change.
* Good, because it removes both defective rules.
* Bad, because it stops checking that unresolved calls are emitted with enough to locate them (FR-40 AC-1).

### Fork 4 — What `reproducibility` compares

**(a) One pinned re-run against the scored graph's hash. ✅ Chosen.**
* Good, because it tests the graph being scored, so a non-reproducible graph fails.
* Good, because drift in the source, tool or environment skips instead of failing, and one run replaces
  three.
* Bad, because the source must be re-acquired, the manifest gains a fingerprint and an envelope record,
  and a scorecard taken in another environment skips.

**(b) Self-consistency renamed, plus a separate FR-34 check.**
* Good, because extractor determinism stays measured on its own.
* Good, because FR-34 AC-3 gains a dedicated check.
* Bad, because it costs four Pass-0 runs and two checks for one property.

**(c) Status quo, documented.**
* Good, because it costs nothing.
* Good, because the documentation would be accurate.
* Bad, because the check keeps passing on graphs that are not reproducible.

### Fork 5 — The `coverage` slot's inputs

**(a) Read the render audit. ✅ Chosen.**
* Good, because the input exists in the designed layout, verified like the compile-check record.
* Good, because FR-7 AC-2 is met and the band becomes calibratable.
* Bad, because evaluation depends on render having written its audit.

**(b) Defer to v1.1.**
* Good, because it costs nothing in v1.
* Good, because it is honest.
* Bad, because it reverses Fork 4's three-slot lock while the input already exists, and FR-7 AC-2 stays
  unmet.

**(c) Render coverage.**
* Good, because it is trivially computable.
* Good, because it needs no feature mapping.
* Bad, because under the cap it is a tautology (ADR-017 rejected it for that reason).

### Fork 6 — Re-validating the annotations file

**(a) Extend `schema_validity`.**
* Good, because one check covers both files.
* Good, because no new check id.
* Bad, because the deterministic check's subject becomes partly LLM-derived, and one value hides which file
  failed.

**(b) A new check. ✅ Chosen.**
* Good, because each check has one subject.
* Good, because it skips cleanly when there are no annotations.
* Bad, because the scorecard gains a check id.

**(c) Write-time validation only.**
* Good, because it costs nothing.
* Good, because write-time validation exists in principle (FR-7b AC-1).
* Bad, because FR-7b AC-2 requires an independent re-check, and a file edited after writing goes unseen.

## More Information

### Relationships

* **ADR-017** (evaluation framework) — this ADR supersedes Fork 3's definitions of four checks and Fork 4's
  coverage definition; everything else in ADR-017 stands.
* **ADR-003** (parsing strategy) — the source of the unresolved-call shape Fork 3 checks (§5).
* **ADR-006** (knowledge graph schema) — the annotation-key join that Fork 3 enforces.
* **ADR-007** (golden-graph pattern) — the envelope Fork 4 records is the one its harness pins.
* **ADR-009** (rendering budget cap) — selection and domains; the startup check for manual mappings.
* **ADR-010** (Spring → TypeScript/NestJS mapping) — the feature matrix and the render audit's contents.
* **ADR-021** (determinism contract, v1.1) — absorbs or cites Fork 4's envelope rule.
* **ADR-025** (manifest schema) — the corpus fingerprint, envelope and Pass-0 settings, and the render
  audit's manifest entry.
* **ADR-026** (release version management) — the cluster's version consequences.
* **ADR-029** (output layout and ownership) — the render audit's location.
* **ADR-033** (extraction environment and parser failures) — the resolution record and transient flag
  Fork 4 reads.
* **ADR-034** (placeholders for unrendered classes) — a placeholder translates none of its class's
  features (Fork 5).
* **ADR-020** (LLM-judge calibration, v1.1) — `semantic_accuracy` remains its deferred check; it consumes
  FR-41's expectation for the semantic half.

### Requirements touched

FR-1 AC-3 · FR-7 AC-2, AC-4 · FR-7a AC-1, AC-2 · FR-7b AC-1, AC-2 · FR-18 AC-1 · FR-30 AC-1, AC-2 ·
FR-34 AC-3, AC-4 · FR-38 AC-2 · FR-40 AC-1 · FR-41 AC-3, AC-4 · NFR-6 AC-4 · NFR-7 AC-3.

### Lessons

ADR-017's check definitions were written as formulas without auditing their operands — where each input
comes from, and whether it can differ from the thing being judged. Three failure shapes followed: an
oracle supplied by the component under test (`structural_completeness`); a denominator constructed so the
ratio cannot move (`relationship_correctness`); and a comparison that never reads its subject
(`reproducibility`). Each check reported green, so CI never surfaced them; they were found by asking what
each number actually means. The definitions in this ADR state their inputs, the conditions under which
each comparison is valid, and the skip for each missing input; every one has a Confirmation item asserting
a hand-worked value.

### References

* Requirements — `docs/requirements.md` (FR-7, FR-7a, FR-7b, FR-18, FR-34, FR-40, FR-41, NFR-6, NFR-7).
* ADR-017 — the definitions superseded here, and the threshold model and skip taxonomy they use.

### Deferred

* The FR-41 expectation artefact and its authoring process — its own ADR, when FR-41 is scheduled (v1.1).
* `semantic_accuracy` and `llm_judge` — ADR-020 (v1.1).
