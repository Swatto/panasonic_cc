# Dev environment

Use `uv` for all Python tooling in this project — running scripts, inspecting packages, type checking, tests.

```bash
uv sync --dev                          # install/update .venv
uv run scripts/explore_aquarea.py      # live device inspection (needs .env)
uv run mypy custom_components/panasonic_cc/ --ignore-missing-imports
uv run python -c "import aioaquarea; ..."  # inspect installed packages
uv add <pkg>                           # add/bump a dep (updates pyproject.toml + uv.lock)
```

Never use bare `python`, `pip`, or `find .venv` — always go through `uv run` or `uv add`.

# Panasonic API — rate limit warning

**Do NOT hit the real Panasonic/Aquarea API in automated contexts.**
Panasonic aggressively blocks clients and IPs that auth too frequently.

Rules:
- Run `explore_aquarea.py` at most once per session, manually.
- Never loop it, never run it in CI against the real API.
- All automated tests must mock `aioaquarea.Client` entirely — never call the real API.
- Never test auth flows in a tight retry loop.
