#!/usr/bin/env python3
"""Script 2: Detect Python version for every repo in a GitHub org."""

import sys
from github_utils import detect_python_version, get_file_tree, list_repos


def main():
    if len(sys.argv) < 2:
        print("Usage: python repo-py-versions.py <org>", file=sys.stderr)
        sys.exit(1)

    org = sys.argv[1]
    for repo in list_repos(org):
        name_with_owner = repo["nameWithOwner"]
        file_tree = get_file_tree(name_with_owner)
        lang, version = detect_python_version(name_with_owner, file_tree)

        if lang == "not-python":
            print(f"{name_with_owner}\tnot-python")
        else:
            print(f"{name_with_owner}\tpython\t{version or 'unknown'}")


if __name__ == "__main__":
    main()
