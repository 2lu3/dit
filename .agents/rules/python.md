---
applies_to: [all]
---

# Python

## Package Manager

- MUST use **uv** (`uv`, `uv add`, `uv remove`, `uv sync`, `uv run`)
- NEVER use `pip`, `pip install`, `poetry`, or `conda` for dependency management
- MUST use `uv add` instead of manually editing `pyproject.toml` / `requirements.txt`
- During upgrade work, if a dependency turns out to be unused, MUST propose removing it (`uv remove`) instead of upgrading it
