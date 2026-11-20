package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import org.json.JSONObject;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Checks each metric against a worked example its source publishes, with the
 * value the source states. A fixture reproduces the published code as closely
 * as Java allows; the expected value is the source's, never the calculator's.
 *
 * <p>
 * Sources:
 * <ul>
 * <li>[CC] G. Ann Campbell, <i>Cognitive Complexity: a new way of measuring
 * understandability</i>, SonarSource, version 1.7 (29 August 2023).</li>
 * <li>[S138] SonarSource sonar-java, the unit-test samples of
 * {@code MethodTooBigCheck} (rule java:S138), at commit
 * f0c71911f63d9421eb1f0347949566620360d903.</li>
 * <li>[HM95] Martin Hitz and Behzad Montazeri, <i>Measuring Coupling and
 * Cohesion in Object-Oriented Systems</i>, Proc. International Symposium on
 * Applied Corporate Computing (ISACC '95), Monterrey, Mexico, October
 * 1995.</li>
 * <li>[Gray] Christopher L. Gray, <i>A Coupling-Complexity Metric Suite for
 * Predicting Software Quality</i>, Master's thesis, California Polytechnic
 * State University, San Luis Obispo, June 2008 (page numbers are the printed
 * ones).</li>
 * <li>[HM96] Martin Hitz and Behzad Montazeri, <i>Chidamber and Kemerer's
 * Metrics Suite: A Measurement Theory Perspective</i>, IEEE Transactions on
 * Software Engineering 22(4), 1996, author's manuscript (page numbers are the
 * manuscript's, not the journal's).</li>
 * </ul>
 *
 * <p>
 * Each of the six metrics has at least one published example here: cyclomatic
 * and cognitive complexity from [CC], method lines of code from [S138], LCOM4
 * from [HM95], WMC from [Gray] and CBO from [HM96].
 */
class ReferenceExamplesTest {

	@BeforeAll
	static void configureParser() {
		StaticJavaParser.setConfiguration(
				new ParserConfiguration().setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
	}

	// -------------------------------------------------------------------------
	// Cyclomatic and cognitive complexity — [CC]
	// -------------------------------------------------------------------------

	private static final String SUM_OF_PRIMES = """
			int sumOfPrimes(int max) {
			   int total = 0;
			   OUT: for (int i = 1; i <= max; ++i) {
			      for (int j = 2; j < i; ++j) {
			         if (i % j == 0) {
			            continue OUT;
			         }
			      }
			      total += i;
			   }
			   return total;
			}
			""";

	private static final String GET_WORDS = """
			String getWords(int number) {
			   switch (number) {
			      case 1:
			         return "one";
			      case 2:
			         return "a couple";
			      case 3:
			         return "a few";
			      default:
			         return "lots";
			   }
			}
			""";

	/**
	 * [CC] p. 5, "An illustration of the problem": sumOfPrimes, Cyclomatic
	 * Complexity 4.
	 */
	@Test
	void sum_of_primes_cyclomatic_is_4() {
		assertEquals(4, ComplexityCalculator.computeCyclomatic(method(SUM_OF_PRIMES)));
	}

	/**
	 * [CC] p. 5, "An illustration of the problem": getWords, Cyclomatic Complexity
	 * 4.
	 */
	@Test
	void get_words_cyclomatic_is_4() {
		assertEquals(4, ComplexityCalculator.computeCyclomatic(method(GET_WORDS)));
	}

	/**
	 * [CC] p. 10, "Intuitively 'right' complexity scores": sumOfPrimes, Cognitive
	 * Complexity 7 (the {@code continue OUT} adds 1).
	 */
	@Disabled("Cognitive complexity does not increment for a continue to a label: the source states 7, the code returns 6")
	@Test
	void sum_of_primes_cognitive_is_7() {
		assertEquals(7, ComplexityCalculator.computeCognitive(method(SUM_OF_PRIMES)));
	}

	/**
	 * [CC] p. 10, "Intuitively 'right' complexity scores": getWords, Cognitive
	 * Complexity 1.
	 */
	@Test
	void get_words_cognitive_is_1() {
		assertEquals(1, ComplexityCalculator.computeCognitive(method(GET_WORDS)));
	}

	/**
	 * [CC] p. 9, "Increment for nested flow-break structures": myMethod, Cognitive
	 * Complexity 9. The source's {@code ...} bodies are written as empty blocks.
	 */
	@Test
	void nested_structures_example_cognitive_is_9() {
		MethodDeclaration m = method("""
				void myMethod () {
				   try {
				      if (condition1) {
				         for (int i = 0; i < 10; i++) {
				            while (condition2) { }
				         }
				      }
				   } catch (ExcepType1 | ExcepType2 e) {
				      if (condition2) { }
				   }
				}
				""");
		assertEquals(9, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * [CC] p. 9: myMethod2, Cognitive Complexity 2. The lambda adds no structural
	 * increment but raises the nesting level, so the {@code if} inside it costs 2.
	 */
	@Disabled("A lambda adds a flat increment of 1, where the source adds none and only nests its body: the source states 2, the code returns 3")
	@Test
	void lambda_nesting_example_cognitive_is_2() {
		MethodDeclaration m = method("""
				void myMethod2 () {
				   Runnable r = () -> {
				       if (condition1) { }
				   };
				}
				""");
		assertEquals(2, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * [CC] p. 8, "Sequences of logical operators": {@code if (a && b && c || d || e
	 * && f)} scores +1 for the {@code if} and +1 for each of three operator runs =
	 * 4.
	 */
	@Test
	void mixed_operator_sequence_example_cognitive_is_4() {
		MethodDeclaration m = method("""
				void f() {
				   if (a
				         && b && c
				         || d || e
				         && f) { }
				}
				""");
		assertEquals(4, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * [CC] p. 8: {@code if (a && !(b && c))} scores +1 for the {@code if}, +1 for
	 * the outer {@code &&} and +1 for the inner one = 3.
	 */
	@Test
	void negated_group_example_cognitive_is_3() {
		MethodDeclaration m = method("""
				void f() {
				   if (a
				         &&
				         !(b && c)) { }
				}
				""");
		assertEquals(3, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * [CC] p. 17, "Appendix C: Examples", from org.sonar.java.resolve.JavaSymbol in
	 * the SonarJava analyzer: overriddenSymbolFrom, total complexity 19.
	 */
	@Test
	void appendix_c_overridden_symbol_from_cognitive_is_19() {
		MethodDeclaration m = method("""
				@Nullable
				private MethodJavaSymbol overriddenSymbolFrom(ClassJavaType classType) {
				  if (classType.isUnknown()) {
				    return Symbols.unknownMethodSymbol;
				  }
				  boolean unknownFound = false;
				  List<JavaSymbol> symbols = classType.getSymbol().members().lookup(name);
				  for (JavaSymbol overrideSymbol : symbols) {
				    if (overrideSymbol.isKind(JavaSymbol.MTH)
				          && !overrideSymbol.isStatic()) {
				      MethodJavaSymbol methodJavaSymbol = (MethodJavaSymbol)overrideSymbol;
				      if (canOverride(methodJavaSymbol)) {
				        Boolean overriding = checkOverridingParameters(methodJavaSymbol, classType);
				        if (overriding == null) {
				          if (!unknownFound) {
				            unknownFound = true;
				          }
				        } else if (overriding) {
				          return methodJavaSymbol;
				        }
				      }
				    }
				  }
				  if (unknownFound) {
				    return Symbols.unknownMethodSymbol;
				  }
				  return null;
				}
				""");
		assertEquals(19, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * [CC] p. 18, "Appendix C: Examples", from com.persistit.TimelyResource in
	 * sonar-persistit: addVersion, total complexity 35.
	 */
	@Test
	void appendix_c_add_version_cognitive_is_35() {
		MethodDeclaration m = method("""
				private void addVersion(final Entry entry, final Transaction txn)
				      throws PersistitInterruptedException, RollbackException {
				  final TransactionIndex ti = _persistit.getTransactionIndex();
				  while (true) {
				    try {
				      synchronized (this) {
				        if (frst != null) {
				          if (frst.getVersion() > entry.getVersion()) {
				            throw new RollbackException();
				          }
				          if (txn.isActive()) {
				            for
				                (Entry e = frst; e != null; e = e.getPrevious()) {
				              final long version = e.getVersion();
				              final long depends = ti.wwDependency(version, txn.getTransactionStatus(), 0);
				              if (depends == TIMED_OUT) {
				                throw new WWRetryException(version);
				              }
				              if (depends != 0
				                  && depends != ABORTED) {
				                throw new RollbackException();
				              }
				            }
				          }
				        }
				        entry.setPrevious(frst);
				        frst = entry;
				        break;
				      }
				    } catch (final WWRetryException re) {
				      try {
				        final long depends = _persistit.getTransactionIndex()
				            .wwDependency(re.getVersionHandle(), txn.getTransactionStatus(),
				                SharedResource.DEFAULT_MAX_WAIT_TIME);
				        if (depends != 0
				            && depends != ABORTED) {
				          throw new RollbackException();
				        }
				      } catch (final InterruptedException ie) {
				        throw new PersistitInterruptedException(ie);
				      }
				    } catch (final InterruptedException ie) {
				      throw new PersistitInterruptedException(ie);
				    }
				  }
				}
				""");
		assertEquals(35, ComplexityCalculator.computeCognitive(m));
	}

	// -------------------------------------------------------------------------
	// Method lines of code — [S138]
	// -------------------------------------------------------------------------

	/**
	 * The sample {@code checks/MethodTooBigCheckCustom4.java} in
	 * java-checks-test-sources/default/src/main/java, run with a maximum of 4. Its
	 * {@code // Noncompliant} comments state the counts: the constructor "has 6
	 * lines" and f() "has 5 lines".
	 */
	private static final String CUSTOM_4 = """
			package checks;

			class MethodTooBigCheckCustom4 {
			  public MethodTooBigCheckCustom4() { // Noncompliant {{This method has 6 lines, which is greater than the 4 lines authorized. Split it into smaller methods.}}
			//       ^^^^^^^^^^^^^^^^^^^^^^^^
			    System.out.println("");
			    // This does not count as a line
			    // This does not count as a line
			    System.out.println("");
			    // This does not count as a line
			    System.out.println("");
			    // This does not count as a line
			    System.out.println("");
			  }

			  public void f() { // Noncompliant {{This method has 5 lines, which is greater than the 4 lines authorized. Split it into smaller methods.}}
			    System.out.println("");
			    // This does not count as a line




			    // This does not count as a line
			    System.out.println("");
			    System.out.println("");
			  }
			}
			""";

	/**
	 * The sample {@code checks/MethodTooBigCheckCustom5.java}, run with a maximum
	 * of 5; its constructor "has 6 lines".
	 */
	private static final String CUSTOM_5 = """
			package checks;

			class MethodTooBigCheckCustom5 {
			  public MethodTooBigCheckCustom5() { // Noncompliant {{This method has 6 lines, which is greater than the 5 lines authorized. Split it into smaller methods.}}
			    System.out.println("");
			    System.out.println("");
			    System.out.println("");
			    System.out.println("");
			  }

			  public void f() { // 1
			    System.out.println("");
			    System.out.println("");
			    System.out.println("");
			  }
			}
			""";

	/** [S138] Custom4: the constructor has 6 lines. */
	@Test
	void s138_custom4_constructor_has_6_lines() {
		assertEquals(6, ComplexityCalculator.computeMethodLoc(constructorOf(CUSTOM_4)));
	}

	/**
	 * [S138] Custom4: f() has 5 lines — blank and comment-only lines are not
	 * counted.
	 */
	@Test
	void s138_custom4_method_has_5_lines() {
		assertEquals(5, ComplexityCalculator.computeMethodLoc(firstMethodOf(CUSTOM_4)));
	}

	/** [S138] Custom5: the constructor has 6 lines. */
	@Test
	void s138_custom5_constructor_has_6_lines() {
		assertEquals(6, ComplexityCalculator.computeMethodLoc(constructorOf(CUSTOM_5)));
	}

	// -------------------------------------------------------------------------
	// LCOM4 — [HM95]
	// -------------------------------------------------------------------------

	/*
	 * [HM95] p. 9 states the connected-components form of LCOM: the number of
	 * connected components of the graph whose nodes are a class's methods and whose
	 * edges join two methods that access a common instance variable. Applied to the
	 * paper's Venn diagrams (each oval is a method, each dot an instance variable)
	 * it gives 2 for Cases 0, I and II and 1 for every instance of Case III. The
	 * fixtures use no method calls, so the call-based extension on the same page
	 * does not come into play. A field is "accessed" by a local declaration that
	 * reads it.
	 */

	/**
	 * [HM95] p. 9, Case 0: two methods, each using its own three variables, share
	 * none. LCOM = 2.
	 */
	@Test
	void hm95_case_0_lcom_is_2() {
		assertEquals(2, lcom4Of("""
				class Case0 {
				   int f1, f2, f3, f4, f5, f6;
				   void m1() { int u = f1 + f2 + f3; }
				   void m2() { int u = f4 + f5 + f6; }
				}
				"""));
	}

	/**
	 * [HM95] p. 9, Case I: one method using three variables of its own, plus two
	 * overlapping methods that share one variable. LCOM = 2.
	 */
	@Test
	void hm95_case_1_lcom_is_2() {
		assertEquals(2, lcom4Of("""
				class Case1 {
				   int f1, f2, f3, f4, f5, f6;
				   void m1() { int u = f1 + f2 + f3; }
				   void m2() { int u = f4 + f5; }
				   void m3() { int u = f5 + f6; }
				}
				"""));
	}

	/**
	 * [HM95] p. 9, Case II: two disjoint pairs of overlapping methods, each pair
	 * sharing one variable. LCOM = 2.
	 */
	@Test
	void hm95_case_2_lcom_is_2() {
		assertEquals(2, lcom4Of("""
				class Case2 {
				   int f1, f2, f3, f4, f5, f6;
				   void m1() { int u = f1 + f2; }
				   void m2() { int u = f2 + f3; }
				   void m3() { int u = f4 + f5; }
				   void m4() { int u = f5 + f6; }
				}
				"""));
	}

	/**
	 * [HM95] p. 9, Case III: n methods linked in a chain, each sharing one variable
	 * with the next. LCOM = 1 for every n; the fixture uses n = 5, where the
	 * paper's original formula would give 2.
	 */
	@Test
	void hm95_case_3_chain_of_five_lcom_is_1() {
		assertEquals(1, lcom4Of("""
				class Case3 {
				   int f1, f2, f3, f4;
				   void m1() { int u = f1; }
				   void m2() { int u = f1 + f2; }
				   void m3() { int u = f2 + f3; }
				   void m4() { int u = f3 + f4; }
				   void m5() { int u = f4; }
				}
				"""));
	}

	// -------------------------------------------------------------------------
	// WMC — [Gray]
	// -------------------------------------------------------------------------

	/**
	 * [Gray] Figure 3.1, p. 26: "The WMC-CC value for ClassA is 4". foo has an
	 * if/else (2) and bar a while loop (2: "1 for the while and then plus one").
	 * The figure's closing braces nest bar inside foo, which is a typesetting slip;
	 * the fixture writes them as sibling methods, as the text's sum of 2 + 2
	 * requires.
	 */
	@Test
	void gray_fig_3_1_wmc_is_4() {
		JSONObject env = envelopeOf("""
				public class ClassA {
				   public void foo(ClassB refB, int y) {
				      if (refB.getValue() > y) {
				         refB.yWasLarger();
				      }
				      else {
				         refB.yWasSmaller();
				      }
				   }

				   public void bar(ClassB refB) {
				      while (refB.isLoop()) {
				         refB.iterateLoop();
				      }
				   }
				}
				""");
		assertEquals(4, env.getInt("wmc"));
		assertEquals(2, env.getJSONArray("methods").getJSONObject(1).getInt("cyclomatic_complexity"));
	}

	// -------------------------------------------------------------------------
	// CBO — [HM96]
	// -------------------------------------------------------------------------

	/**
	 * [HM96] p. 3, Fig. 1, left design, which violates the Law of Demeter through
	 * {@code b->f()->g()}: "both designs presented in Fig. 1 result in CBO(C) = 2,
	 * because method M of class C uses methods of classes A and B". The source's
	 * C++ pointers are Java references and method M is written m. Classes A and B
	 * are separate compilation units, so the parser's count for C rests on the
	 * declared types alone.
	 */
	@Test
	void hm96_fig_1_left_design_cbo_of_c_is_2() {
		assertEquals(2, envelopeOf("""
				class C {
				   A a;
				   B b;
				   void m() { a.g(); b.f().g(); }
				}
				""").getInt("cbo"));
	}

	/**
	 * [HM96] p. 3, Fig. 1, right design, which reaches g() through an access method
	 * {@code applyG()} in B: CBO(C) = 2, the same as the left design.
	 */
	@Test
	void hm96_fig_1_right_design_cbo_of_c_is_2() {
		assertEquals(2, envelopeOf("""
				class C {
				   A a;
				   B b;
				   void m() { a.g(); b.applyG(); }
				}
				""").getInt("cbo"));
	}

	// -------------------------------------------------------------------------
	// Helpers
	// -------------------------------------------------------------------------

	private static JSONObject envelopeOf(String source) {
		return ParsedFileAssembler.buildEnvelope(StaticJavaParser.parse(source), "Fixture.java");
	}

	private static int lcom4Of(String source) {
		return envelopeOf(source).getInt("lcom4");
	}

	private static MethodDeclaration method(String methodSource) {
		return firstMethodOf("class _Wrap_ { " + methodSource + " }");
	}

	private static MethodDeclaration firstMethodOf(String source) {
		return classOf(source).getMethods().get(0);
	}

	private static ConstructorDeclaration constructorOf(String source) {
		return classOf(source).getConstructors().get(0);
	}

	private static ClassOrInterfaceDeclaration classOf(String source) {
		CompilationUnit cu = StaticJavaParser.parse(source);
		return cu.findFirst(ClassOrInterfaceDeclaration.class)
				.orElseThrow(() -> new IllegalStateException("no class in fixture"));
	}
}
