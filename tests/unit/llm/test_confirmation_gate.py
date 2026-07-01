from unittest.mock import patch

import click
import pytest

from codeograph.llm.confirmation_gate import ConfirmationGate


def test_confirmation_gate_under_threshold():
    """Verify that gate proceeds if total calls are below the threshold."""
    gate = ConfirmationGate(threshold=100)
    # Under threshold should proceed without checking TTY or prompting
    gate.check(total_calls=50)

def test_confirmation_gate_over_threshold_waived():
    """Verify that gate proceeds if waived by yes or non_interactive."""
    gate = ConfirmationGate(threshold=100)

    with patch.object(gate, "is_tty") as mock_is_tty, patch("click.confirm") as mock_confirm:
        gate.check(total_calls=150, yes=True)
        mock_is_tty.assert_not_called()
        mock_confirm.assert_not_called()

    with patch.object(gate, "is_tty") as mock_is_tty, patch("click.confirm") as mock_confirm:
        gate.check(total_calls=150, non_interactive=True)
        mock_is_tty.assert_not_called()
        mock_confirm.assert_not_called()    

def test_confirmation_gate_non_tty_abort():
    """Verify that gate auto-aborts in a non-TTY environment if over threshold."""
    gate = ConfirmationGate(threshold=100)

    with patch.object(gate, "is_tty", return_value=False):
        with pytest.raises(click.ClickException) as exc_info:
            gate.check(total_calls=150)

        message = str(exc_info.value)
        assert "--yes" in message
        assert "--non-interactive" in message


def test_confirmation_gate_tty_prompt_accept():
    """Verify that gate proceeds on a TTY if user confirms."""
    gate = ConfirmationGate(threshold=100)
    with patch.object(gate, "is_tty", return_value=True):
        with patch("click.confirm", return_value=True) as mock_confirm:
            gate.check(total_calls=150)

            mock_confirm.assert_called_once()


def test_confirmation_gate_tty_prompt_reject():
    """Verify that gate aborts on a TTY if user rejects."""
    gate = ConfirmationGate(threshold=100)

    with patch.object(gate, "is_tty", return_value=True):
        with patch("click.confirm", return_value=False) as mock_confirm:
            with pytest.raises(click.Abort):
                gate.check(total_calls=150)

            mock_confirm.assert_called_once()