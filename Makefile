.PHONY: help schema-models lint typecheck test golden-update format format-java clean

PYTHON ?= python

help:
	@echo "Targets:"
	@echo "  schema-models   Regenerate Pydantic models from JSON Schema"
	@echo "  lint            Run ruff lint + format check"
	@echo "  typecheck       Run mypy"
	@echo "  test            Run full test suite"
	@echo "  golden-update   Refresh golden graph files"
	@echo "  format          Format Python (ruff) + Java (spotless)"
	@echo "  format-java     Apply google-java-format via Spotless (run once on first setup)"
	@echo "  clean           Remove generated artefacts"

# Regenerate Pydantic models from JSON Schema files into codeograph/graph/models/.
# Multiple schema files → output must be a directory (codegen produces one .py per schema).
# CI runs this and then checks 'git diff --exit-code' to ensure generated files are fresh.
schema-models:
	$(PYTHON) -m datamodel_code_generator \
		--input codeograph/schema/ \
		--input-file-type jsonschema \
		--output codeograph/graph/models/ \
		--output-model-type pydantic_v2.BaseModel \
		--field-constraints \
		--use-standard-collections \
		--use-union-operator \
		--use-annotated

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy codeograph/

test:
	pytest tests/ -x

format:
	ruff format .
	ruff check --fix .
	$(MAKE) format-java

format-java:
	cd codeograph/parser/java && mvn spotless:apply --batch-mode --no-transfer-progress

# Refresh golden graph files for all corpora.
# Tier 1 + Tier 2 only; Tier 3 (JHipster) is nightly-only.
golden-update:
	pytest tests/test_golden.py --update-goldens -k "not tier3"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage
