#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path


def process_file(filepath: Path) -> bool:
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        return False

    try:
        parts = content.split("---", 2)
        if len(parts) < 3:
            return False
        pre, fm, body = parts
    except ValueError:
        return False

    body_normalized = "\n".join(line.rstrip() for line in body.splitlines()) + "\n"
    actual_hash = hashlib.sha256(body_normalized.encode("utf-8")).hexdigest()[:8]

    new_fm_lines = []
    found_pin = False
    for line in fm.splitlines():
        if line.startswith("content_hash_pin:"):
            new_fm_lines.append(f"content_hash_pin: {actual_hash}")
            found_pin = True
        else:
            new_fm_lines.append(line)

    if not found_pin:
        # Add it if missing
        new_fm_lines.append(f"content_hash_pin: {actual_hash}")

    new_fm = "\n".join(new_fm_lines)
    new_content = f"---{new_fm}\n---{body}"

    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False


def main():
    changed = False
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.exists() and p.suffix == ".md":
            if process_file(p):
                changed = True
                print(f"Updated hash pin for {p}")

    if changed:
        sys.exit(1)  # pre-commit needs exit 1 to fail if it modified files


if __name__ == "__main__":
    main()
