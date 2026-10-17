#!/usr/bin/env python3
"""griffe_diff.py — API breaking-change diff between two PyPI versions of a package.

Runs INSIDE the repo venv (uv run python tools/griffe_diff.py pkg old new).
Downloads both wheels from PyPI, extracts them, loads each with griffe,
and prints a markdown report of formal API breaking changes.
Exit 0 always (report may say "no breakages" or warn on failure) —
the caller embeds the output in the PR body.
"""
import json
import re
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def download_and_extract(pkg: str, version: str, dest: Path) -> Path | None:
    with urllib.request.urlopen(
        f"https://pypi.org/pypi/{pkg}/{version}/json", timeout=30
    ) as r:
        urls = [u for u in json.load(r)["urls"] if u["packagetype"] == "bdist_wheel"]
    if not urls:
        return None
    dest.mkdir(parents=True, exist_ok=True)
    wheel = dest / urls[0]["filename"]
    urllib.request.urlretrieve(urls[0]["url"], wheel)
    pkgdir = dest / "pkg"
    with zipfile.ZipFile(wheel) as z:
        z.extractall(pkgdir)
    return pkgdir


def main():
    pkg, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        import griffe
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            old_dir = download_and_extract(pkg, old, tmp / "old")
            new_dir = download_and_extract(pkg, new, tmp / "new")
            if not old_dir or not new_dir:
                print(f"⚠️ griffe : wheel introuvable sur PyPI pour `{pkg}` — vérification manuelle requise.")
                return
            # griffe needs the import name (underscores), not the PyPI project name (hyphens)
            import_name = pkg.replace("-", "_")
            old_api = griffe.load(import_name, search_paths=[old_dir])
            new_api = griffe.load(import_name, search_paths=[new_dir])
            breakages = list(griffe.find_breaking_changes(old_api, new_api))
            if not breakages:
                print(f"✅ griffe : aucun breaking change d'API formel détecté pour `{pkg}` `{old}` → `{new}`.")
                return
            lines = [f"### 🔎 API breaking changes (griffe) : `{pkg}` `{old}` → `{new}`", ""]
            for b in breakages:
                # Strip ANSI colours and shorten local temp paths to `module/path.py:line`
                text = ANSI_RE.sub("", b.explain())
                text = re.sub(rf"{re.escape(str(tmp))}/(old|new)/pkg/", "", text)
                lines.append(f"- **[{b.kind.name}]** {text}")
            print("\n".join(lines))
    except Exception as e:
        print(f"⚠️ griffe a échoué ({type(e).__name__}: {e}) — vérification manuelle requise.")


if __name__ == "__main__":
    main()
