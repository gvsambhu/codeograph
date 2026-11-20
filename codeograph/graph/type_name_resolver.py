"""
TypeNameResolver — turns the type names a parser reports as written
(superclass, interfaces, field, return and parameter types, referenced types)
into fully-qualified class names.

The parser sees one file at a time, so it can only report a type the way the
source spells it. The corpus-wide graph stage knows every class in the
project, which is what makes a same-package name resolvable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from codeograph.graph.models.graph_schema import Node

# A (possibly dotted) type name inside a type expression such as
# ``Map<String, List<? extends Pet>>[]``; annotations and the bound keywords are removed first.
_NAME = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")
_ANNOTATION = re.compile(r"@[\w$.]+(?:\([^)]*\))?")
_BOUND_KEYWORDS = frozenset({"extends", "super"})


class TypeNameResolver:
    """
    Resolves a type name by four rules, in Java's own order, applied to the
    name's first segment:

      1. an explicit single-type import of that name → the imported FQCN;
      2. a class of that name in the file's own package, if the corpus
         declares it → ``<package>.<name>``;
      3. a class of that name in a package the file imports on demand
         (``import com.example.model.*;``), if the corpus declares it in
         exactly one of those packages → ``<package>.<name>``; two or more
         packages declaring it is a name Java would reject as ambiguous, so it
         stays as written;
      4. otherwise the name stays as written.

    A nested type written with its outer type (``Map.Entry``, ``Order.Builder``)
    is resolved through its first segment, and the remaining segments are
    appended: ``Map.Entry`` with ``import java.util.Map`` becomes
    ``java.util.Map.Entry``. A dotted name whose first segment starts in
    lowercase is a package (Java convention) and is already qualified; it is
    returned unchanged. A name that no rule resolves — an external type reached
    through a wildcard import that the corpus does not declare, or a ``java.lang``
    type — stays as written.
    """

    def __init__(self, corpus_type_ids: set[str]) -> None:
        """:param corpus_type_ids: FQCN of every type declared in the corpus."""
        self._corpus_type_ids = corpus_type_ids

    def declares(self, fqcn: str) -> bool:
        """True if the corpus declares the type ``fqcn`` (a resolved name)."""
        return fqcn in self._corpus_type_ids

    def resolve(
        self, name: str, package: str, import_map: dict[str, str], wildcard_packages: Sequence[str] = ()
    ) -> str:
        """
        :param name:              the type name as written in the source.
        :param package:           package of the file that names it ("" for the default package).
        :param import_map:        the file's explicit imports, simple name → FQCN.
        :param wildcard_packages: the packages the file imports on demand.
        """
        outer, dot, rest = name.partition(".")
        if dot and outer[:1].islower():
            return name
        resolved = import_map.get(outer)
        if not resolved:
            same_package = f"{package}.{outer}" if package else outer
            resolved = same_package if same_package in self._corpus_type_ids else None
        if not resolved:
            on_demand = {f"{p}.{outer}" for p in wildcard_packages if f"{p}.{outer}" in self._corpus_type_ids}
            resolved = next(iter(on_demand)) if len(on_demand) == 1 else None
        if not resolved:
            return name
        return f"{resolved}{dot}{rest}"

    def resolve_type_expression(
        self, expression: str, package: str, import_map: dict[str, str], wildcard_packages: Sequence[str] = ()
    ) -> list[str]:
        """
        Resolve every class a type expression names, type arguments included.

        ``Map<String, List<Pet>>`` yields the resolved ``Map``, ``String``, ``List``
        and ``Pet``; wildcard bounds (``? extends Pet``) and array element types
        count, the keywords and brackets do not. Primitive names are returned as
        written, so a caller that looks the result up in the corpus finds nothing.

        :param expression: a type as written in the source (a field, return or parameter type).
        :param package:    package of the file that names it ("" for the default package).
        :param import_map: the file's explicit imports, simple name → FQCN.
        :param wildcard_packages: the packages the file imports on demand.
        """
        names = _NAME.findall(_ANNOTATION.sub(" ", expression))
        return [
            self.resolve(name, package, import_map, wildcard_packages) for name in names if name not in _BOUND_KEYWORDS
        ]

    def resolve_nodes(
        self,
        nodes: list[Node],
        import_maps: dict[str, dict[str, str]],
        wildcard_imports: Mapping[str, Sequence[str]] | None = None,
    ) -> list[Node]:
        """
        Return the nodes with their superclass, implemented-interface and
        extended-interface names resolved. Nodes that carry none are returned
        as they are; the input nodes are not modified.

        :param import_maps:      per type id, that file's explicit imports (simple name → FQCN).
        :param wildcard_imports: per type id, the packages that file imports on demand.
        """
        wildcards = wildcard_imports or {}
        return [self._resolve_node(node, import_maps, wildcards) for node in nodes]

    def _resolve_node(
        self, node: Node, import_maps: dict[str, dict[str, str]], wildcard_imports: Mapping[str, Sequence[str]]
    ) -> Node:
        model = node.root
        update: dict[str, object] = {}
        package = model.id.rpartition(".")[0]
        import_map = import_maps.get(model.id, {})
        wildcards = wildcard_imports.get(model.id, ())

        superclass = getattr(model, "superclass", None)
        if superclass:
            update["superclass"] = self.resolve(superclass, package, import_map, wildcards)
        for field in ("implements", "extends_interfaces"):
            names = getattr(model, field, None)
            if names:
                update[field] = [self.resolve(n, package, import_map, wildcards) for n in names]

        if not update:
            return node
        return Node(root=model.model_copy(update=update))
