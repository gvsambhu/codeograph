package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import org.json.JSONArray;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for {@link Lcom4Calculator} — LCOM4 metric and connected-components algorithm.
 *
 * <p>Fixtures are chosen to hit the three canonical cases: fully cohesive (1),
 * two isolated groups (2), and a god class with three groups (≥ 3).
 */
class Lcom4CalculatorTest {

    @BeforeAll
    static void configureParser() {
        StaticJavaParser.setConfiguration(
                new ParserConfiguration()
                        .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
    }

    /**
     * Cohesive class: all three methods touch the same field {@code balance}.
     * Graph: deposit — withdraw — getBalance (all connected through balance).
     * Expected LCOM4 = 1.
     */
    private static final String COHESIVE_SOURCE = """
            package com.example;
            public class BankAccount {
                private double balance;

                public void   deposit(double amount)  { balance += amount; }
                public void   withdraw(double amount) { balance -= amount; }
                public double getBalance()            { return balance; }
            }
            """;

    /**
     * Split class: two independent method groups, each touching a different field.
     * Group 1 (order): validate, persist.
     * Group 2 (mailer): sendConfirmation, sendReceipt.
     * Expected LCOM4 = 2.
     */
    private static final String SPLIT_SOURCE = """
            package com.example;
            public class MixedService {
                private String order;
                private String mailer;

                public void validate()         { System.out.println(order); }
                public void persist()          { System.out.println(order); }
                public void sendConfirmation() { System.out.println(mailer); }
                public void sendReceipt()      { System.out.println(mailer); }
            }
            """;

    /**
     * God class: three completely isolated method groups, one per field.
     * Group 1 (userRepo): findUser, saveUser.
     * Group 2 (emailService): sendWelcome, sendAlert.
     * Group 3 (reportEngine): exportPdf, exportCsv.
     * Expected LCOM4 = 3.
     */
    private static final String GOD_SOURCE = """
            package com.example;
            public class ApplicationFacade {
                private String userRepo;
                private String emailService;
                private String reportEngine;

                public void findUser()    { System.out.println(userRepo); }
                public void saveUser()    { System.out.println(userRepo); }
                public void sendWelcome() { System.out.println(emailService); }
                public void sendAlert()   { System.out.println(emailService); }
                public void exportPdf()   { System.out.println(reportEngine); }
                public void exportCsv()   { System.out.println(reportEngine); }
            }
            """;

    @Test
    void lcom4_cohesiveClass_returns1() {
        CompilationUnit cu = StaticJavaParser.parse(COHESIVE_SOURCE);
        ClassOrInterfaceDeclaration decl =
                cu.findFirst(ClassOrInterfaceDeclaration.class).orElseThrow();
        JSONArray methods = ParsedFileAssembler.buildMethods(decl, "com.example.BankAccount");
        assertEquals(1, Lcom4Calculator.computeLcom4(methods));
    }

    @Test
    void lcom4_splitClass_returns2() {
        CompilationUnit cu = StaticJavaParser.parse(SPLIT_SOURCE);
        ClassOrInterfaceDeclaration decl =
                cu.findFirst(ClassOrInterfaceDeclaration.class).orElseThrow();
        JSONArray methods = ParsedFileAssembler.buildMethods(decl, "com.example.MixedService");
        assertEquals(2, Lcom4Calculator.computeLcom4(methods));
    }

    @Test
    void lcom4_godClass_returns3OrMore() {
        CompilationUnit cu = StaticJavaParser.parse(GOD_SOURCE);
        ClassOrInterfaceDeclaration decl =
                cu.findFirst(ClassOrInterfaceDeclaration.class).orElseThrow();
        JSONArray methods = ParsedFileAssembler.buildMethods(decl, "com.example.ApplicationFacade");
        assertTrue(Lcom4Calculator.computeLcom4(methods) >= 3);
    }
}
