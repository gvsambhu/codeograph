from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import click


class MutuallyExclusiveOption(click.Option):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.mutually_exclusive = set(kwargs.pop("mutually_exclusive", []))
        help_text = kwargs.get("help", "")
        if self.mutually_exclusive:
            ex_str = ", ".join(self.mutually_exclusive)
            kwargs["help"] = help_text + f" (Mutually exclusive with: {ex_str})"
        super().__init__(*args, **kwargs)

    def handle_parse_result(
        self,
        ctx: click.Context,
        opts: Mapping[str, Any],
        args: list[str],
    ) -> tuple[Any, list[str]]:
        if self.mutually_exclusive.intersection(opts) and self.name in opts:
            raise click.UsageError(
                f"Illegal usage: `{self.name}` is mutually exclusive with "
                f"arguments `{', '.join(self.mutually_exclusive)}`."
            )
        return super().handle_parse_result(ctx, opts, args)
