# Prior Art & Related Tools

This document is a survey of the tools Codeograph lives next to, not a comparison that ranks them. Its job is to place Codeograph honestly in the landscape — which families it borders, what it borrows, and what it deliberately does not do. The claim it supports is a coverage claim, not a novelty claim.

> **Scope & method.** This document surveys ~14 tools across three adjacent families — code-graph /
> architecture-analysis / quality tools, code-as-data platforms, and graph-/model-driven modernization
> engines — plus the cross-language transpilers that border codeograph's *rendering* layer. Facts were
> web-verified June 2026; only **stable attributes** are recorded (license family, maintenance status,
> internal model). Pricing and exact version numbers are intentionally omitted — they drift and are not
> what distinguishes these tools. Items that could not be pinned are noted inline.

---

## 1. Summary — the landscape at a glance

Codeograph sits at the intersection between static graph-analysis tools and cross-language code generation. It fills a specific gap in that landscape by pairing a deterministic, metrics-carrying property graph with a pluggable cross-language scaffold renderer — a combination no tool in the survey currently provides.

---

## 2. Background: the representation (property graph)

- **What a labeled property graph (LPG) is.** A directed, labeled, attributed multigraph: nodes carry one or more **labels** (type) plus arbitrary key/value **properties**; edges are directed, labeled, and may **also** carry properties; multiple edges may connect the same pair of nodes. (This is what distinguishes an LPG from an RDF triple store, where edges cannot carry properties.)
- **Who uses it for code.** **Neo4j** is the canonical LPG database; **jQAssistant** builds its Java static-analysis model directly on Neo4j (§4.1) — a same-domain example of property-graph-as-representation. The **Code Property Graph (CPG)** — Joern's model (§4.3) — is a named, peer-reviewed property-graph representation *specifically for source code* (merging AST + control-flow + program-dependence); its originating paper won the **IEEE S&P Test-of-Time award (2024)**.
- **It is a standard, not a bespoke choice.** The property-graph query language **GQL** was published as **ISO/IEC 39075:2024** (12 April 2024) — the first new ISO database-language standard since SQL. **openCypher** is the widely-implemented open grammar (Neo4j, Memgraph, SAP HANA Graph, others).

---

## 3. Background: the complexity metrics

| Metric codeograph emits | Originating reference | Cited in full |
|---|---|---|
| Cyclomatic complexity | McCabe 1976 | §8 |
| Cognitive complexity | Campbell / SonarSource 2018 | §8 |
| CK suite (incl. CBO, WMC) | Chidamber & Kemerer 1994 | §8 |
| LCOM4 (cohesion) | Hitz & Montazeri 1995 | §8 |
| OO-metric empirical validation | Basili, Briand & Melo 1996 | §8 |
| Thresholds / detection strategies | Lanza & Marinescu 2006 | §8 |

---

## 4. The tool landscape

A uniform "No" in the cross-language-render column across the analysis and modernization tools is itself the key finding: none of them render a target language from their model.*

### 4.1 Code-graph / architecture-analysis / quality tools

This is the established space of "understand and govern an existing codebase." **jQAssistant** is the in-domain property-graph exemplar — it loads JVM structure into **Neo4j** and validates architecture rules in Cypher. **Structure101** and **Lattix** are commercial architecture-governance tools (layering / Dependency-Structure-Matrix); **Understand** (SciTools) is a broad polyglot static-analysis + metrics IDE; **SourceTrail** was a well-regarded interactive code-comprehension explorer (now discontinued, community forks active); **SonarQube** is the de-facto CI quality-gate platform and the **authoritative source of the Cognitive Complexity metric** (Campbell, §3). *(Boundary note: SpotBugs and PMD are Java bug/style detectors — they find defect patterns over bytecode/AST and do not emit a navigable code graph or scaffold; named only to mark the edge of this family.)* Per-tool facts are in the §5 matrix.

### 4.2 Source-to-source transpilers & AI code converters

These border codeograph's **rendering** layer, but do a different job: **faithful** behaviour-preserving translation, with **no** graph or complexity emission. **JSweet** transpiles Java→TypeScript→JavaScript on top of `javac` + the TS compiler (GPL-3; semi-dormant, seeking a maintainer); **J2CL** (Google, Apache-2.0) and **GWT** (Apache-2.0) compile Java→JavaScript for web apps. Smaller/experimental converters exist (`mike-lischke/java2typescript` for Java→TS; `NickyBoy89/java2go` for experimental Java→Go), as do LLM converters (**CodeConvert AI**, a commercial SaaS) and the research model **Meta TransCoder** (Java↔Python↔C++, not an installable tool). The distinction that matters: a transpiler emits *line-for-line equivalent code*; it does not build a deterministic graph, compute metrics, or scaffold an idiomatic target-framework project.

### 4.3 Code-as-data platforms & graph-driven modernization engines — the closest family

These are the nearest neighbours — tools that build a queryable model of a codebase (often a property graph) and sometimes transform code from it.

- **Joern** — the closest *same-representation* analogue. It builds a **Code Property Graph** (AST + CFG + PDG in one property graph) and queries it via a Scala DSL. Notably, Joern parses Java source with **JavaParser — the same parser codeograph uses** — and stores a property graph; the difference is purpose (security/vulnerability discovery) and that Joern is **analysis-only**: no scaffold or source-to-source emission. Apache-2.0, actively maintained.
- **GitHub CodeQL** — compiles a project into a **relational database** ("code as data") queried in the QL language for SAST and variant analysis, surfaced as code-scanning alerts. Free for open-source/academic; bundled into paid GitHub tiers. **No** scaffold/translation.
- **OpenRewrite / Moderne** — the closest *"build a semantic model, then transform code"* analogue. OpenRewrite refactors via **Lossless Semantic Trees** (type-attributed ASTs) driven by **recipes**, emitting transformed source + diffs; Moderne is the commercial multi-repo layer. Crucially the transformation is **intra-language modernization** (Java→Java with new APIs / dependency upgrades), **not** Java→Go/TS. Apache-2.0 (OpenRewrite) / commercial (Moderne).
- **Others in this family** (see §5): **Sourcegraph** (SCIP/LSIF code intelligence — search/navigation, no transpile); **Meta Glean** (indexes code into typed "facts" queried with Angle); **Spoon** (INRIA — Java→Java analysis + transformation over a `CtModel` AST, MIT); **CAST Imaging** (commercial "software MRI" knowledge graph for modernization *planning*, no source generation); and **Amazon Q Code Transformation** (generative-AI **within-Java** version/framework upgrades — partial, not cross-language).

### 4.4 Name-collision tools (disambiguation only)

> The name *codeograph* sits near several **code-graph** tools — **CodeGraph**, **RepoGraph**, **Coograph** — that build code graphs to give **AI coding agents** navigation context. That is a different category from deterministic analysis or rendering, named here only to prevent reader confusion.

---

## 5. Comparison matrix (facts only)

*Stable attributes only. **Cross-lang render** = does it generate a different target language from its model? "Partial" = same-language transform (e.g., Java→Java), not a cross-language scaffold.*

| Tool | Family | Languages | Internal model | Primary use case | Cross-lang render? | License (family) | Maintenance |
|---|---|---|---|---|---|---|---|
| jQAssistant | code-graph / quality | Java/JVM (+ plugins) | **Property graph (Neo4j)** | Architecture governance / rule validation | No | GPL-3 (OSS) | Active |
| Structure101 | architecture | Java-first | Structure/dependency map (DSM-style); no exposed graph store | Architecture governance / layering | No | Commercial | In transition — acquired by Sonar (2024-10) |
| SourceTrail | comprehension | C, C++, Java, Python | Cross-ref graph (SQLite store) | Code comprehension / navigation | No | GPL-3 (OSS) | Discontinued 2021 (forks active) |
| Understand (SciTools) | static analysis | 12+ (Ada, C/C++, C#, COBOL, FORTRAN, Java, Python…) | Proprietary entity/reference DB | Static analysis + comprehension + metrics | No | Commercial | Active |
| Lattix | architecture | Software (Java+) + SysML/UML | **Dependency Structure Matrix (DSM)** | Architecture governance (DSM) | No | Commercial | Active |
| SonarQube | quality / SAST | 20+ (Community) / 30+ (paid) | Issue/measure model (no exposed graph) | Quality gate + code-quality/security | No | LGPL-3 (Community) + paid editions | Active |
| Joern | code-as-data | C/C++, Java, JS, Python, Kotlin, PHP, bytecode, binaries | **Code Property Graph (CPG)** | Security / vulnerability analysis | No | Apache-2.0 (OSS) | Active |
| GitHub CodeQL | code-as-data | Java, JS/TS, C/C++, C#, Go, Python, Ruby, Swift, Kotlin | Relational DB (QL queries) | SAST / variant analysis | No | Free OSS + paid (bundled) | Active |
| Sourcegraph (SCIP/LSIF) | code intelligence | Go, TS/JS, Java, Python, C#… | SCIP binary index | Code search / navigation | No | Commercial + open SCIP spec | Active |
| Meta Glean | code-as-data | polyglot (ingests LSIF/SCIP) | Fact DB (Angle query language) | Code search / xref backend | No | Open source | Active |
| Spoon (INRIA) | analysis + transform | Java | AST metamodel (`CtModel`, Eclipse JDT) | Java analysis + transformation | Partial (Java→Java) | MIT (OSS) | Active |
| CAST Imaging | code-as-data | 150+ technologies | Knowledge graph | App discovery / modernization planning | No | Commercial | Active |
| OpenRewrite / Moderne | modernization | Java (+Spring), JS/TS, YAML, POM… | **Lossless Semantic Tree (LST)** | Automated refactoring / migration recipes | No (Java→Java) | Apache-2.0 (OSS) / commercial | Active |
| Amazon Q Code Transformation | modernization | Java (+SQL dialects; .NET emerging) | Not publicly detailed (gen-AI) | Java version/framework upgrades | Partial (within-Java) | Bundled (Amazon Q Developer) | Active |

---

## 6. Where Codeograph fits

Codeograph sits at a seam the survey leaves open: one family builds deterministic, metrics-carrying property graphs and stops at analysis, while another renders code into a new stack without ever building or trusting a graph. Joern-style graph tools and OpenRewrite-class transformers each cover one half; transpilers and LLM converters cover the other, but without graph grounding. That is a coverage claim, not a novelty claim: the graph and its metrics are established prior art, and the pairing is what Codeograph adds.

In v1, that pairing produces TypeScript/NestJS scaffolds, with Go planned for v1.1. Where idioms or security features cannot be rendered deterministically, the output leaves TODO markers instead of silent drops, and compile/eval gates backstop what is emitted. The graph remains authoritative; the rendering layer is a helper, not a decision-maker.

---

## 7. What Codeograph deliberately does NOT do (non-goals)

- **Not a faithful, behaviour-preserving transpiler.** Codeograph emits a deterministic graph and structural scaffolds; it does not perform 1:1 line-by-line translation of business logic. For faithful transpilation, use JSweet, J2CL, or a dedicated transpiler.
- **Not architecture governance or rule enforcement.** It maps the structure that exists, but does not validate layering, enforce dependency rules, or apply architecture constraints. For governance, use jQAssistant, Structure101, or Lattix.
- **Not a security SAST engine.** It does not track taint flows, detect CVEs, or model attack surfaces. For vulnerability analysis, use Joern or GitHub CodeQL.
- **Not same-language modernization or automated refactoring.** It does not upgrade framework versions, migrate deprecated APIs, or apply refactoring recipes within Java. For automated Java refactoring, use OpenRewrite/Moderne.
- **Not a multi-language renderer in v1.** The first release renders TypeScript/NestJS scaffolds exclusively; Java→Go rendering is a planned v1.1 extension, and renderers are pluggable per target stack.
- **Not an autonomous agent that "understands" the codebase.** LLM summaries and scaffold output are advisory; the deterministic graph is authoritative, and core logic in rendered scaffolds carries TODO markers for humans to finish.

---

## 8. References

**Complexity metrics**
1. McCabe, T. J. (1976). "A Complexity Measure." *IEEE Transactions on Software Engineering*, SE-2(4), 308–320. DOI 10.1109/TSE.1976.233837.
2. Campbell, G. A. (2018). "Cognitive Complexity: An Overview and Evaluation." *TechDebt '18*. DOI 10.1145/3194164.3194186. (SonarSource white paper, 2018.)
3. Chidamber, S. R., & Kemerer, C. F. (1994). "A Metrics Suite for Object-Oriented Design." *IEEE TSE*, 20(6), 476–493. DOI 10.1109/32.295895.
4. Hitz, M., & Montazeri, B. (1995). "Measuring Coupling and Cohesion in Object-Oriented Systems." *ISACC '95*, Monterrey. (Proceedings; no DOI.)
5. Basili, V. R., Briand, L. C., & Melo, W. L. (1996). "A Validation of Object-Oriented Design Metrics as Quality Indicators." *IEEE TSE*, 22(10), 751–761. DOI 10.1109/32.544352.
6. Lanza, M., & Marinescu, R. (2006). *Object-Oriented Metrics in Practice.* Springer. ISBN 978-3-540-24429-5.

**Representation / property graph**
7. Yamaguchi, F., Golde, N., Arp, D., & Rieck, K. (2014). "Modeling and Discovering Vulnerabilities with Code Property Graphs." *2014 IEEE Symposium on Security and Privacy*, 590–604. DOI 10.1109/SP.2014.44.
8. ISO/IEC 39075:2024 — *Information technology — Database languages — GQL.* Published 2024-04-12. https://www.iso.org/standard/76120.html
9. openCypher. https://opencypher.org/

**Tools** (canonical project/vendor pages, accessed June 2026)
- jQAssistant — https://jqassistant.github.io/
- Structure101 — https://structure101.com/
- SourceTrail — https://github.com/CoatiSoftware/Sourcetrail
- Understand (SciTools) — https://scitools.com/
- Lattix — https://www.lattix.com/
- SonarQube — https://www.sonarsource.com/
- Joern — https://joern.io/ · https://github.com/joernio/joern
- GitHub CodeQL — https://codeql.github.com/
- Sourcegraph / SCIP — https://sourcegraph.com/ · https://scip-code.org/
- Meta Glean — https://glean.software/
- Spoon — https://github.com/INRIA/spoon
- CAST Imaging — https://www.castsoftware.com/imaging
- OpenRewrite / Moderne — https://docs.openrewrite.org/ · https://www.moderne.ai/
- Amazon Q Code Transformation — https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/code-transformation.html
- JSweet — https://www.jsweet.org/ · J2CL — https://github.com/google/j2cl · GWT — https://www.gwtproject.org/

---

## 9. Survey method

Surveyed ~14 tools across three adjacent families plus the transpiler border, June 2026, from primary/vendor sources. Only stable attributes are recorded (license family, maintenance status, internal model); pricing and exact versions are omitted as volatile. A few non-disclosed commercial internals (e.g., Amazon Q's model) are marked "not publicly detailed" rather than inferred.
