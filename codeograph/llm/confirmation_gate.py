import sys
import click

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
        if total_calls <= self._threshold:
            return

        if yes or non_interactive:
            return

        if self.is_tty():
            confirmed = click.confirm(
                f"Estimated calls ({total_calls}) exceed threshold ({self._threshold}). Proceed?"
            )
            if not confirmed:
                raise click.Abort()
            return

        raise click.ClickException(
            f"Estimated calls ({total_calls}) exceed threshold ({self._threshold}) in a "
            "non-interactive run. Re-run with --yes or --non-interactive to proceed."
        )