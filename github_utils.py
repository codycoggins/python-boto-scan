"""Shared GitHub CLI utilities for boto3/Python version scanning scripts."""

import base64
import json
import re
import subprocess
import time

import tomllib
from packaging.specifiers import SpecifierSet
from packaging.version import Version

# Python version candidates to probe when finding minimum from a SpecifierSet
_PROBE_VERSIONS = [Version(f"3.{m}") for m in range(0, 20)]


# ---------------------------------------------------------------------------
# GitHub CLI helpers
# ---------------------------------------------------------------------------

def run_gh(*args) -> dict | list:
    """Run a gh CLI command, parse JSON output, raise on error."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh command failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def list_repos(org: str) -> list[dict]:
    """Return non-archived, non-fork repos for org as [{name, nameWithOwner}]."""
    return run_gh(
        "repo", "list", org,
        "--no-archived", "--source",
        "--json", "name,nameWithOwner",
        "--limit", "1000",
    )


def get_file_tree(owner_repo: str) -> list[str]:
    """Return all file paths in the repo via recursive git tree API."""
    try:
        data = run_gh("api", f"repos/{owner_repo}/git/trees/HEAD?recursive=1")
    except RuntimeError:
        return []
    return [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]


def get_file_content(owner_repo: str, path: str) -> str | None:
    """Fetch file content from GitHub, base64-decode it. Returns None on 404."""
    time.sleep(0.1)
    try:
        data = run_gh("api", f"repos/{owner_repo}/contents/{path}")
    except RuntimeError:
        return None
    encoded = data.get("content", "")
    return base64.b64decode(encoded).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# boto3 detection
# ---------------------------------------------------------------------------

def find_boto3_repos(org: str) -> list[str]:
    """Return sorted list of nameWithOwner strings for repos containing boto3."""
    repos = list_repos(org)
    valid_repos = {r["nameWithOwner"] for r in repos}

    results = run_gh(
        "search", "code", "boto3",
        "--owner", org,
        "--json", "repository,path",
        "--limit", "1000",
    )

    boto3_repos = set()
    for item in results:
        name_with_owner = item["repository"]["nameWithOwner"]
        if name_with_owner in valid_repos:
            boto3_repos.add(name_with_owner)

    return sorted(boto3_repos)


# ---------------------------------------------------------------------------
# Python version detection
# ---------------------------------------------------------------------------

def _min_version_from_specifier(spec_str: str) -> str | None:
    """Return minimum Python 3.x version string implied by a specifier like '>=3.9'."""
    spec_str = spec_str.strip()
    # Normalize caret ranges (^3.9 → >=3.9)
    spec_str = re.sub(r"\^(\d+\.\d+)", r">=\1", spec_str)
    try:
        spec = SpecifierSet(spec_str)
    except Exception:
        m = re.search(r"(\d+\.\d+)", spec_str)
        return m.group(1) if m else None

    for v in _PROBE_VERSIONS:
        if v in spec:
            return str(v)
    return None


def _version_from_dockerfile(content: str) -> str | None:
    for line in content.splitlines():
        m = re.match(r"^\s*FROM\s+python:(\d+\.\d+)", line, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _version_from_pyproject(content: str) -> str | None:
    try:
        data = tomllib.loads(content)
    except Exception:
        return None
    spec_str = (
        data.get("project", {}).get("requires-python")
        or data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python")
    )
    if spec_str:
        return _min_version_from_specifier(spec_str)
    return None


def _version_from_setup_cfg(content: str) -> str | None:
    m = re.search(r"python_requires\s*=\s*([^\n]+)", content)
    if m:
        return _min_version_from_specifier(m.group(1).strip())
    return None


def _version_from_setup_py(content: str) -> str | None:
    m = re.search(r"python_requires\s*=\s*['\"]([^'\"]+)['\"]", content)
    if m:
        return _min_version_from_specifier(m.group(1))
    return None


def detect_python_version(owner_repo: str, file_tree: list[str]) -> tuple[str, str | None]:
    """
    Detect the Python version used by a repo.

    Returns (lang, version) where:
      - lang is 'python' or 'not-python'
      - version is a version string, or None (meaning 'unknown')
    """
    py_extensions = {".py", ".pyx", ".pxd"}
    has_python_files = any(
        any(p.endswith(ext) for ext in py_extensions)
        for p in file_tree
    )

    # Priority 1: Dockerfile
    dockerfiles = [p for p in file_tree if re.search(r"(^|/)Dockerfile", p)]
    for df_path in dockerfiles:
        content = get_file_content(owner_repo, df_path)
        if content:
            v = _version_from_dockerfile(content)
            if v:
                return ("python", v)

    # Priority 2: pyproject.toml — prefer root (fewest path separators), then subdirs
    pyprojects = sorted(
        [p for p in file_tree if p.endswith("pyproject.toml")],
        key=lambda p: p.count("/"),
    )
    for pp_path in pyprojects:
        content = get_file_content(owner_repo, pp_path)
        if content:
            v = _version_from_pyproject(content)
            if v:
                return ("python", v)
            has_python_files = True  # pyproject.toml implies Python project

    # Priority 3: .python-version
    if ".python-version" in file_tree:
        content = get_file_content(owner_repo, ".python-version")
        if content:
            v = content.strip().splitlines()[0].strip()
            if v:
                return ("python", v)

    # Priority 4: runtime.txt
    if "runtime.txt" in file_tree:
        content = get_file_content(owner_repo, "runtime.txt")
        if content:
            v = content.strip().removeprefix("python-")
            if v:
                return ("python", v)

    # Priority 5: setup.cfg
    for sc_path in [p for p in file_tree if p.endswith("setup.cfg")]:
        content = get_file_content(owner_repo, sc_path)
        if content:
            v = _version_from_setup_cfg(content)
            if v:
                return ("python", v)
            has_python_files = True

    # Priority 6: setup.py
    for sp_path in [p for p in file_tree if p.endswith("setup.py")]:
        content = get_file_content(owner_repo, sp_path)
        if content:
            v = _version_from_setup_py(content)
            if v:
                return ("python", v)
            has_python_files = True

    if not has_python_files:
        return ("not-python", None)

    return ("python", None)
