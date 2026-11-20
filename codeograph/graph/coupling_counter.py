"""
CouplingCounter — sets each class's CBO (Coupling Between Objects).

Sets ``ClassNode.cbo`` from the whole corpus, since the count needs three things
one file cannot supply: the referenced type names resolved to classes, the
classes the class's methods call, and which classes are the corpus's and which
the JDK's.
"""

from __future__ import annotations

from collections import defaultdict

from codeograph.graph.jdk_classifier import JdkClassifier
from codeograph.graph.models.graph_schema import ClassNode, Edge, Node
from codeograph.graph.type_name_resolver import TypeNameResolver
from codeograph.parser.models import ParsedFile


class CouplingCounter:
    """
    CBO = the number of distinct classes, other than the class itself, its own
    nested types and the JDK's, that the class references (ADR-004 §3.4):

      - the type names the parser reports for field types, parameter types,
        return types, locally declared variable types and throws clauses,
        type arguments included, resolved to FQCNs by :class:`TypeNameResolver`;
      - the classes of the class's resolved call targets
        (``calls_resolved`` edges whose source is one of its methods).

    A class of the corpus is never the JDK's, whatever its name. Otherwise a
    resolved name is a JDK class if its package is a package the committed JDK
    list names, and a name with no package is one if it is a ``java.lang`` type
    or a type of a package the file imports on demand (:class:`JdkClassifier`). A
    nested type of the class itself is the class: the parser reports it
    qualified with the class's name, which this check drops with the class.

    A class whose parsed file carries no ``referenced_types`` (regex fallback)
    keeps the parser's own count.
    """

    def __init__(self, resolver: TypeNameResolver, jdk: JdkClassifier | None = None) -> None:
        """:param jdk: decides which names are the JDK's; defaults to the committed JDK list."""
        self._resolver = resolver
        self._jdk = jdk or JdkClassifier.committed()

    def apply(
        self,
        nodes: list[Node],
        corpus_files: list[ParsedFile],
        import_maps: dict[str, dict[str, str]],
        edges: list[Edge],
    ) -> list[Node]:
        """
        Return the nodes with every class's ``cbo`` set; other nodes are returned
        as they are, and the input nodes are not modified.

        :param corpus_files: every parsed file of the corpus.
        :param import_maps:  per type id, that file's explicit imports (simple name → FQCN).
        :param edges:        the corpus's edges, calls already resolved.
        """
        files = {pf["id"]: pf for pf in corpus_files}
        called = self._called_classes(edges)
        return [self._with_cbo(node, files, called, import_maps) for node in nodes]

    def _with_cbo(
        self,
        node: Node,
        files: dict[str, ParsedFile],
        called: dict[str, set[str]],
        import_maps: dict[str, dict[str, str]],
    ) -> Node:
        model = node.root
        parsed_file = files.get(model.id)
        names = parsed_file.get("referenced_types") if parsed_file else None
        if not isinstance(model, ClassNode) or parsed_file is None or names is None:
            return node

        package = model.id.rpartition(".")[0]
        import_map = import_maps.get(model.id, {})
        wildcards = parsed_file.get("wildcard_imports", [])
        classes = {self._resolver.resolve(name, package, import_map, wildcards) for name in names}
        classes = {c for c in classes if self._resolver.declares(c) or not self._jdk.is_jdk(c, wildcards)}
        classes |= called.get(model.id, set())
        own_nested = f"{model.id}."
        classes = {c for c in classes if c != model.id and not c.startswith(own_nested)}
        return Node(root=model.model_copy(update={"cbo": len(classes)}))

    @staticmethod
    def _called_classes(edges: list[Edge]) -> dict[str, set[str]]:
        """class FQCN → FQCNs of the classes its methods call (resolved calls only)."""
        called: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            if edge.root.kind == "calls_resolved":
                called[edge.root.source.split("#")[0]].add(edge.root.target.split("#")[0])
        return called
