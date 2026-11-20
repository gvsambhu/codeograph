"""Unit tests for JdkClassifier and the committed JDK list."""

from __future__ import annotations

import json
from importlib import resources

from codeograph.graph.jdk_classifier import JdkClassifier

_SMALL = JdkClassifier(
    {
        "java.lang": ["String", "Record"],
        "java.util": ["Date", "Map"],
        "javax.sql": ["DataSource"],
    }
)


class TestJdkClassifier:
    def test_a_qualified_name_is_the_jdk_if_its_package_is_listed(self):
        assert _SMALL.is_jdk("java.util.Date")
        assert _SMALL.is_jdk("javax.sql.DataSource")

    def test_a_qualified_name_in_an_unlisted_package_is_not(self):
        assert not _SMALL.is_jdk("javax.persistence.EntityManager")
        assert not _SMALL.is_jdk("com.example.Date")

    def test_a_nested_qualified_name_uses_its_package(self):
        assert _SMALL.is_jdk("java.util.Map.Entry")

    def test_a_java_lang_name_without_a_package_is_the_jdk(self):
        assert _SMALL.is_jdk("String")
        assert _SMALL.is_jdk("Record")

    def test_other_names_without_a_package_are_not(self):
        assert not _SMALL.is_jdk("Date")
        assert not _SMALL.is_jdk("Owner")

    def test_an_on_demand_import_makes_its_listed_types_the_jdk(self):
        assert _SMALL.is_jdk("Date", ["java.util"])
        assert _SMALL.is_jdk("Map.Entry", ["java.util"])
        assert not _SMALL.is_jdk("Owner", ["java.util"])

    def test_an_on_demand_import_of_an_unlisted_package_adds_nothing(self):
        assert not _SMALL.is_jdk("Date", ["com.example.util"])

    def test_a_name_with_no_type_segment_is_not_the_jdk(self):
        assert not _SMALL.is_jdk("java.util")


class TestCommittedList:
    def test_the_committed_list_names_its_jdk_and_is_sorted(self):
        data = json.loads(resources.files("codeograph.graph").joinpath("jdk_types.json").read_text(encoding="utf-8"))
        assert data["jdk"]
        packages = data["packages"]
        assert list(packages) == sorted(packages)
        assert all(names == sorted(names) for names in packages.values())

    def test_the_committed_classifier_knows_the_types_cbo_depends_on(self):
        jdk = JdkClassifier.committed()
        assert jdk.is_jdk("StringBuilder")
        assert jdk.is_jdk("NumberFormatException")
        assert jdk.is_jdk("Date", ["java.util"])
        assert jdk.is_jdk("javax.sql.DataSource")
        assert jdk.is_jdk("java.util.Map.Entry")

    def test_the_committed_classifier_does_not_take_java_ee_apis_for_the_jdk(self):
        jdk = JdkClassifier.committed()
        assert not jdk.is_jdk("javax.persistence.EntityManager")
        assert not jdk.is_jdk("javax.servlet.http.HttpServletRequest")
        assert not jdk.is_jdk("jakarta.persistence.EntityManager")

    def test_the_committed_classifier_is_one_shared_instance(self):
        assert JdkClassifier.committed() is JdkClassifier.committed()
