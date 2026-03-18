#!/usr/bin/env python3
"""Script 3: Flag repos that use boto3 and need Python version remediation."""

import argparse
import sys

from packaging.version import Version

from github_utils import detect_python_version, find_boto3_repos, get_file_tree

BOTO3_EOL_VERSION = Version("3.9")


def _parse_version(version_str: str | None) -> Version | None:
    if not version_str or version_str == "unknown":
        return None
    try:
        return Version(version_str)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Find boto3 repos needing Python remediation before boto3 drops 3.9 support."
    )
    parser.add_argument("org", help="GitHub org or user to scan")
    parser.add_argument(
        "--boto3-list",
        metavar="FILE",
        help="File with pre-computed boto3 repos (one nameWithOwner per line)",
    )
    args = parser.parse_args()

    if args.boto3_list:
        with open(args.boto3_list) as f:
            boto3_repos = [line.strip() for line in f if line.strip()]
    else:
        boto3_repos = find_boto3_repos(args.org)

    needs_remediation = []
    unknown_version = []
    safe = []

    for name_with_owner in boto3_repos:
        file_tree = get_file_tree(name_with_owner)
        _, version_str = detect_python_version(name_with_owner, file_tree)
        version = _parse_version(version_str)

        if version is None:
            unknown_version.append(name_with_owner)
        elif version <= BOTO3_EOL_VERSION:
            needs_remediation.append((name_with_owner, str(version)))
        else:
            safe.append((name_with_owner, str(version)))

    print(f"=== NEEDS REMEDIATION (boto3 + Python <= {BOTO3_EOL_VERSION}) ===")
    if needs_remediation:
        for repo, v in needs_remediation:
            print(f"  {repo}\tpython {v}")
    else:
        print("  (none)")

    print()
    print("=== UNKNOWN VERSION (boto3 found, Python version undetectable) ===")
    if unknown_version:
        for repo in unknown_version:
            print(f"  {repo}")
    else:
        print("  (none)")

    print()
    print("=== SAFE (boto3 + Python >= 3.10) ===")
    if safe:
        for repo, v in safe:
            print(f"  {repo}\tpython {v}")
    else:
        print("  (none)")

    print()
    print(
        f"Summary: {len(needs_remediation)} need remediation, "
        f"{len(unknown_version)} unknown, "
        f"{len(safe)} safe"
    )


if __name__ == "__main__":
    main()
