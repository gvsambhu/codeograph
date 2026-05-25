from jinja2 import Environment
from jinja2.meta import find_undeclared_variables

from codeograph.llm.prompts.models import Prompt


class PromptValidationError(Exception):
    pass


_META_ENV = Environment(
    variable_start_string="<<",
    variable_end_string=">>",
    block_start_string="<%",
    block_end_string="%>",
    comment_start_string="<#",
    comment_end_string="#>",
)


def _extract_jinja_vars(template_source: str) -> set[str]:
    ast = _META_ENV.parse(template_source)
    return find_undeclared_variables(ast)


def _validate(prompt: Prompt) -> None:
    body_vars = _extract_jinja_vars(prompt.user) | _extract_jinja_vars(prompt.system)
    declared = set(prompt.metadata.required_vars) | set(prompt.metadata.optional_vars)
    missing_in_declaration = body_vars - declared
    unused_declarations = set(prompt.metadata.required_vars) - body_vars

    if missing_in_declaration or unused_declarations:
        raise PromptValidationError(
            f"Prompt {prompt.id} v{prompt.version}: "
            f"undeclared body vars: {missing_in_declaration}; "
            f"declared-but-unused required vars: {unused_declarations}"
        )
