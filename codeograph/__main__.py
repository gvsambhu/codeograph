"""Allow ``python -m codeograph`` invocation (used by check_reproducibility)."""

from codeograph.cli.main import cli

if __name__ == "__main__":
    cli()
