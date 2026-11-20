package io.codeograph.parser;

import java.util.List;
import java.util.Set;

/**
 * Shared constants for the codeograph Java parser.
 *
 * <p>
 * All string lists are first-match-wins ordered where order matters
 * (STEREOTYPES). Sets are unordered lookup tables (CBO_EXCLUDED_TYPES).
 */
final class ParserConstants {

	private ParserConstants() {
	}

	/**
	 * Spring stereotype annotation names in first-match-wins priority order
	 * (ADR-003 §9 — stereotypes category). Values match the graph schema enum.
	 */
	static final List<String> STEREOTYPES = List.of("Component", "Service", "Repository", "Controller",
			"RestController", "Configuration", "ControllerAdvice", "Entity", "SpringBootApplication");

	/**
	 * Annotations that signal field injection (@Autowired = Spring, @Inject =
	 * JSR-330).
	 */
	static final List<String> AUTOWIRE_ANNOTATIONS = List.of("Autowired", "Inject");

	/** Annotation that narrows which bean to inject by name or qualifier value. */
	static final String QUALIFIER_ANNOTATION = "Qualifier";

	/**
	 * Bean Validation (JSR-380) constraint annotations relevant for the graph
	 * schema.
	 */
	static final List<String> CONSTRAINT_ANNOTATIONS = List.of("NotNull", "NotBlank", "NotEmpty", "Size", "Min", "Max",
			"Email", "Pattern");

	/**
	 * Type names left out of the parser's own per-file CBO (Coupling Between
	 * Objects) count: boxed types and ubiquitous java.lang / java.util classes.
	 * This is a hand-picked subset and is not what decides the JDK for the
	 * corpus-wide count, which the graph stage takes from the committed JDK list;
	 * referenced_types is not filtered by it.
	 *
	 * CBO reference: Chidamber & Kemerer (1994), "A Metrics Suite for Object
	 * Oriented Design", IEEE TSE 20(6), 476–493.
	 */
	static final Set<String> CBO_EXCLUDED_TYPES = Set.of(
			// primitives
			"void", "int", "long", "double", "float", "boolean", "char", "byte", "short",
			// boxed primitives + java.lang staples
			"String", "Object", "Integer", "Long", "Double", "Float", "Boolean", "Character", "Byte", "Short", "Number",
			// common collection containers (element type is the coupling signal, not the
			// container)
			"List", "Set", "Map", "Collection", "Iterable", "Optional", "ArrayList", "LinkedList", "HashMap", "HashSet",
			"LinkedHashMap",
			// functional / stream
			"Stream", "Function", "Consumer", "Supplier", "Predicate", "BiFunction",
			// misc java.lang
			"Class", "Enum", "Record", "Comparable", "Cloneable",
			// java.lang exceptions and errors, which throws clauses name routinely
			"Throwable", "Exception", "RuntimeException", "Error", "IllegalArgumentException", "IllegalStateException",
			"UnsupportedOperationException", "NullPointerException", "IndexOutOfBoundsException", "ClassCastException",
			"ArithmeticException", "InterruptedException", "CloneNotSupportedException",
			// type-inference placeholder
			"var");
}
