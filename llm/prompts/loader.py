import hashlib
from pathlib import Path
import yaml
from codeograph.llm.prompts.models import Prompt, PromptMetadata
from codeograph.llm.prompts.validation import _validate, PromptValidationError

class PromptLoadError(Exception):
    pass

class PromptLoader:
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._cache: dict[str, Prompt] = {}

    def get(self, prompt_id: str, version: str | None = None) -> Prompt:
        prompt_dir = self._base_dir / prompt_id
        if not prompt_dir.exists():
            raise PromptLoadError(f"Prompt directory not found: {prompt_dir}")

        if version is None:
            alias_file = prompt_dir / "default.yaml"
            if not alias_file.exists():
                raise PromptLoadError(f"No version specified and default.yaml missing in {prompt_dir}")
            with open(alias_file, "r", encoding="utf-8") as f:
                alias_data = yaml.safe_load(f)
            version = alias_data.get("default")
            if not version:
                raise PromptLoadError(f"default.yaml missing 'default' key in {prompt_dir}")

        cache_key = f"{prompt_id}:{version}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt_file = prompt_dir / f"{version}.md"
        if not prompt_file.exists():
            raise PromptLoadError(f"Prompt file not found: {prompt_file}")

        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.startswith("---"):
            raise PromptLoadError(f"Missing YAML frontmatter in {prompt_file}")

        try:
            _, frontmatter_text, body = content.split("---", 2)
        except ValueError:
            raise PromptLoadError(f"Malformed YAML frontmatter in {prompt_file}")

        fm_data = yaml.safe_load(frontmatter_text.strip())
        if not fm_data:
            raise PromptLoadError(f"Empty YAML frontmatter in {prompt_file}")

        pin = fm_data.get("content_hash_pin")
        if not pin:
            raise PromptLoadError(f"content_hash_pin is REQUIRED in {prompt_file}")

        metadata = PromptMetadata(
            id=fm_data.get("id", prompt_id),
            version=fm_data.get("version", version),
            purpose=fm_data.get("purpose", ""),
            required_vars=fm_data.get("required_vars", []),
            optional_vars=fm_data.get("optional_vars", []),
            cacheable_segments=fm_data.get("cacheable_segments", []),
            content_hash_pin=pin
        )

        body_normalized = "\n".join(line.rstrip() for line in body.splitlines()) + "\n"
        actual_hash = hashlib.sha256(body_normalized.encode("utf-8")).hexdigest()[:8]

        if actual_hash != pin:
            raise PromptLoadError(f"content_hash_pin mismatch in {prompt_file}: expected {pin}, got {actual_hash}")

        system_segment = ""
        user_segment = ""
        
        # Simple extraction based on standard headers per ADR-014
        if "# System" in body_normalized and "# User" in body_normalized:
            parts = body_normalized.split("# System", 1)[1].split("# User", 1)
            system_segment = parts[0].strip()
            user_segment = parts[1].strip()
        else:
            user_segment = body_normalized.strip()

        prompt = Prompt(
            id=prompt_id,
            version=version,
            metadata=metadata,
            system=system_segment,
            user=user_segment,
            content_hash=actual_hash
        )

        _validate(prompt)
        self._cache[cache_key] = prompt
        return prompt
