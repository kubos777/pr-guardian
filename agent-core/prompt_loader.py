"""Prompt Loader — Loads and validates prompt templates from the prompts/ directory."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"

REQUIRED_PROMPTS = ["style_prompt.md", "security_prompt.md", "history_prompt.md"]

REQUIRED_SECTIONS = ["## Role", "## Output Format", "## Example Output", "## Anti-Hallucination Rules"]


def load_prompt(name: str) -> str:
    """Load a single prompt file by name and return its content."""
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def validate_prompt(name: str, content: str) -> list[str]:
    """Validate that a prompt contains all required sections. Returns list of missing sections."""
    missing = []
    for section in REQUIRED_SECTIONS:
        if section not in content:
            missing.append(section)
    return missing


def load_all_prompts() -> dict[str, str]:
    """Load all required prompts and validate their structure."""
    prompts = {}
    for name in REQUIRED_PROMPTS:
        content = load_prompt(name)
        missing = validate_prompt(name, content)
        if missing:
            raise ValueError(f"Prompt '{name}' is missing sections: {missing}")
        prompts[name] = content
    return prompts


if __name__ == "__main__":
    print("=" * 60)
    print("PR Guardian — Prompt Loader Test")
    print("=" * 60)

    prompts = load_all_prompts()

    for name, content in prompts.items():
        lines = content.strip().splitlines()
        print(f"\n✓ {name}")
        print(f"  - Lines: {len(lines)}")
        print(f"  - Size: {len(content)} chars")
        print(f"  - Title: {lines[0] if lines else '(empty)'}")
        print(f"  - Sections found: {sum(1 for s in REQUIRED_SECTIONS if s in content)}/{len(REQUIRED_SECTIONS)}")

    print("\n" + "=" * 60)
    print(f"All {len(prompts)} prompts loaded and validated successfully.")
    print("=" * 60)
