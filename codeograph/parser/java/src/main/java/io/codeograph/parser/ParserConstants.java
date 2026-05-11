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
	 * Type names excluded from CBO (Coupling Between Objects) counting.
	 *
	 * Excludes Java primitives, boxed types, and ubiquitous java.lang / java.util
	 * classes whose presence does not indicate meaningful coupling to a domain
	 * type. Keeping this conservative avoids inflating CBO with noise.
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
			// type-inference placeholder
			"var");
}
