import sys


class ConfirmationGate:
    """Orchestrates TTY-aware confirmation prompts when estimated calls exceed a threshold."""

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold

    def is_tty(self) -> bool:
        """Check if stdin is a TTY (interactive terminal session)."""
        return sys.stdin.isatty()

    def check(self, total_calls: int, yes: bool = False, non_interactive: bool = False) -> None:
        """Evaluate estimated call count against the threshold.

        Raises:
            click.Abort: If user rejects the prompt on a TTY.
            click.ClickException: If threshold is exceeded in a non-TTY run without waiver.
        """
        # TODO(learner): Implement confirmation logic:
        # 1. If total_calls <= self._threshold, return immediately.
        # 2. If yes or non_interactive is True, proceed without check/prompt.
        # 3. Otherwise:
        #    - If self.is_tty() is True (interactive TTY session):
        #      Use click.confirm("Estimated calls ({total_calls}) exceed threshold ({self._threshold}). Proceed?")
        #      If not confirmed, raise click.Abort().
        #    - If self.is_tty() is False (non-interactive CI/pipeline):
        #      Raise click.ClickException indicating estimated calls exceed threshold and
        #      requesting --yes or --non-interactive override.
        raise NotImplementedError("To be implemented by the learner.")
