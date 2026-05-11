package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import org.json.JSONObject;

import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * JavaParserRunner — CLI entry point for the codeograph Java parser.
 *
 * <p>
 * Usage:
 *
 * <pre>
 *   java -jar parser.jar &lt;absolute-path-to-file.java&gt; &lt;corpus-root&gt;
 * </pre>
 *
 * <p>
 * Outputs one JSON envelope to stdout (UTF-8). Exits 0 on success, 1 on parse
 * failure. All errors go to stderr so stdout stays clean JSON.
 *
 * <p>
 * Delegates all extraction and assembly to {@link ParsedFileAssembler}. Invoked
 * per-file by the Python pipeline (ADR-003). The Python side falls back to
 * regex extraction if this process exits non-zero.
 */
public class JavaParserRunner {

	public static void main(String[] args) {
		if (args.length < 2) {
			System.err.println("Usage: parser.jar <java-file> <corpus-root>");
			System.exit(1);
		}

		Path javaFile = Paths.get(args[0]);
		Path corpusRoot = Paths.get(args[1]);

		ParserConfiguration config = new ParserConfiguration()
				.setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17);
		StaticJavaParser.setConfiguration(config);

		try {
			CompilationUnit cu = StaticJavaParser.parse(javaFile.toFile());

			String sourceFile = corpusRoot.relativize(javaFile).toString().replace("\\", "/");

			JSONObject envelope = ParsedFileAssembler.buildEnvelope(cu, sourceFile);
			System.out.println(envelope.toString());
			System.exit(0);

		} catch (Exception e) {
			System.err.println("Parse failed: " + e.getMessage());
			System.exit(1);
		}
	}
}
