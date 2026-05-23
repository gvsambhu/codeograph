import pytest
from click.testing import CliRunner
from codeograph.cli.cache import cache_cli

def test_cache_cli_stats(tmp_path):
    runner = CliRunner()
    # TODO(learner): Mock Settings.cache_dir to point to tmp_path, populate db, run command, assert output
    pass

def test_cache_cli_purge_dry_run(tmp_path):
    runner = CliRunner()
    # TODO(learner): Assert purge without --force doesn't delete entries
    pass