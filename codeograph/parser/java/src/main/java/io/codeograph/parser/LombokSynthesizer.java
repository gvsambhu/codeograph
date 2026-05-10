package io.codeograph.parser;

import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;

/**
 * Lombok synthesis pass — adds synthesised method declarations to a class AST
 * node before {@link ParsedFileAssembler} extracts the methods array.
 *
 * <p>Called from {@link ParsedFileAssembler#buildClass} before {@code buildMethods}
 * runs, so synthesised methods appear in the graph exactly like hand-written ones.
 * Each synthesised method carries {@code is_synthesised: true} in the JSON output.
 *
 * <p>Supported annotations (ADR-003 §6):
 * <ul>
 *   <li>{@code @Getter}               — class-level and field-level</li>
 *   <li>{@code @Setter}               — class-level and field-level</li>
 *   <li>{@code @NoArgsConstructor}    — no-arg constructor</li>
 *   <li>{@code @AllArgsConstructor}   — constructor for all fields</li>
 *   <li>{@code @RequiredArgsConstructor} — constructor for final + @NonNull fields</li>
 *   <li>{@code @Data}                 — @Getter + @Setter + @RequiredArgsConstructor
 *                                        + @ToString + @EqualsAndHashCode</li>
 *   <li>{@code @Value}                — immutable @Data variant</li>
 *   <li>{@code @Builder}              — static builder() entry point + nested Builder class</li>
 * </ul>
 *
 * <p>Synthesised methods do NOT contribute to cyclomatic or cognitive complexity
 * (their bodies are empty stubs). Acceptance criterion: {@code is_synthesised: true}
 * in the JSON envelope for each generated method.
 */
final class LombokSynthesizer {

    private LombokSynthesizer() {}

    /**
     * Inspect {@code decl} for Lombok annotations and inject synthesised method
     * declarations directly into the AST node so that the standard
     * {@link ParsedFileAssembler#buildMethods} pass picks them up automatically.
     *
     * <p>Mutates {@code decl} in-place; returns void. The caller (buildClass) does
     * not need to distinguish synthesised from real methods — they all appear in
     * the methods array, differentiated only by the {@code is_synthesised} flag.
     *
     * @param decl the class declaration to enrich (modified in-place)
     */
    static void synthesize(ClassOrInterfaceDeclaration decl) {
        // TODO (learner — Issue #2): examine decl.getAnnotations() for class-level
        // Lombok annotations (@Data, @Value, @Builder, @Getter, @Setter,
        // @NoArgsConstructor, @AllArgsConstructor, @RequiredArgsConstructor).
        //
        // For each annotation present, call the corresponding private helper that
        // adds the appropriate MethodDeclaration(s) to decl.getMembers().
        //
        // Field-level @Getter / @Setter: iterate decl.getFields() and synthesise
        // only for the annotated fields.
        //
        // Mark each added method with a @SynthesisedByLombok marker annotation
        // (or use a name convention) so ParsedFileAssembler can set
        // is_synthesised: true on the resulting JSON object.
        //
        // Hint: use JavaParser's AST builder API —
        //   new MethodDeclaration()
        //     .setName("getX")
        //     .setType("X")
        //     .setModifiers(Modifier.Keyword.PUBLIC)
        //     .setBody(new BlockStmt())   // empty body — complexity stays 0
    }
}
