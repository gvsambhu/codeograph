from jinja2 import Environment, StrictUndefined

_ENV = Environment(
    variable_start_string="<<",
    variable_end_string=">>",
    block_start_string="<%",
    block_end_string="%>",
    comment_start_string="<#",
    comment_end_string="#>",
    keep_trailing_newline=True,
    undefined=StrictUndefined,
    autoescape=False,
)


def render(template_source: str, **vars: object) -> str:
    return _ENV.from_string(template_source).render(**vars)
