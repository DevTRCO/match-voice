"""Print a constraints file: the versions installed in this venv of everything pyproject.toml's runtime dependencies pull in.

    .venv/bin/python backend/scripts/constraints.py > constraints.txt

The Dockerfile installs with `-c constraints.txt`, so a cloud build (az acr build) gets the versions the test suite ran on instead
of whatever is newest that day (agent-framework-anthropic is a prerelease pin). Markers are evaluated for the image: Linux, the
Python of the Dockerfile. A package the closure needs that is not installed here is named on stderr and left unpinned.
"""
from __future__ import annotations

import sys
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
IMAGE = {"python_version": "3.13", "python_full_version": "3.13.3", "sys_platform": "linux", "platform_system": "Linux",
         "os_name": "posix", "platform_machine": "x86_64", "implementation_name": "cpython", "platform_python_implementation": "CPython"}


def main() -> None:
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    seen: dict[str, tuple[str, set[str]]] = {}
    todo, missing = [Requirement(d) for d in deps], set()
    while todo:
        req = todo.pop()
        name = canonicalize_name(req.name)
        try:
            dist = metadata.distribution(req.name)
        except metadata.PackageNotFoundError:
            missing.add(req.name)
            continue
        prev = seen.get(name)
        if prev is not None and set(req.extras) <= prev[1]:
            continue
        extras = (prev[1] if prev else set()) | set(req.extras)
        seen[name] = (dist.version, extras)
        for raw in dist.requires or []:
            sub = Requirement(raw)
            if sub.marker is None or any(sub.marker.evaluate({**IMAGE, "extra": x}) for x in ("", *sorted(extras))):
                todo.append(sub)
    print("# Generated from the tested .venv (pip freeze, filtered to the runtime closure of pyproject.toml for Linux, Python 3.13 like the image).")
    print("# The Docker image installs with -c constraints.txt so the cloud build gets the versions the test suite ran on.")
    print("# Regenerate: .venv/bin/python backend/scripts/constraints.py > constraints.txt")
    for name in sorted(seen):
        print(f"{name}=={seen[name][0]}")
    if missing:
        print("not installed here, left unpinned: " + ", ".join(sorted(missing)), file=sys.stderr)


if __name__ == "__main__":
    main()
