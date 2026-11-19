"""
Source-location credential check.

A source location is the raw ``INPUT`` argument of ``codeograph run``. When it is a URL it can carry
credentials in its userinfo (``https://user:token@host/repo.git``); echoing, logging or recording such
a location would leak the secret into the console, CI logs and run artefacts. This module refuses
those locations up front and renders a safe form for messages.
"""

from __future__ import annotations

import re

from codeograph.input.acquirers.base_acquirer import AcquisitionError

# scheme://authority — the authority runs to the first "/", "?" or "#".
_URL_PREFIX = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*)://(?P<authority>[^/?#]*)")

_ALTERNATIVES = (
    "Pass credentials to git instead: use an SSH key or agent, a git credential helper, "
    "or git's environment-based configuration (GIT_ASKPASS, or GIT_CONFIG_COUNT with an HTTP header)."
)


def _userinfo(location: str) -> tuple[str, str] | None:
    """Return (scheme, userinfo) when ``location`` is a URL with userinfo, else None."""
    match = _URL_PREFIX.match(location)
    if match is None:
        return None
    authority = match.group("authority")
    userinfo, at, _host = authority.rpartition("@")
    if not at or not userinfo:
        return None
    return match.group("scheme").lower(), userinfo


def redact_source_location(location: str) -> str:
    """Return ``location`` with any URL userinfo removed; safe to print or log."""
    match = _URL_PREFIX.match(location)
    if match is None or _userinfo(location) is None:
        return location
    authority = match.group("authority")
    host = authority.rpartition("@")[2]
    return f"{match.group('scheme')}://{host}{location[match.end() :]}"


def carries_secret(location: str) -> bool:
    """True when ``location`` is a URL whose userinfo holds a secret.

    For ``http://`` and ``https://`` any userinfo counts, user part included: a token is commonly
    passed as the user name (``https://<token>@github.com/...``). For other schemes only a password
    counts; a bare user name (``ssh://git@host/...``) is not a secret. The scp-like form
    ``git@host:org/repo.git`` has no password syntax and is never a secret.
    """
    parsed = _userinfo(location)
    if parsed is None:
        return False
    scheme, userinfo = parsed
    if scheme in ("http", "https"):
        return True
    return ":" in userinfo


def ensure_no_credentials(location: str) -> None:
    """Refuse a source location that carries a secret.

    :raises AcquisitionError: with a message that names the alternatives and shows the location with
        its userinfo removed; the secret never appears in the message.
    """
    if carries_secret(location):
        raise AcquisitionError(
            f"Source location {redact_source_location(location)!r} carries credentials; "
            f"refusing to use it. {_ALTERNATIVES}"
        )
