#!/usr/bin/env python3
"""Script 1: Find repos in a GitHub org that contain boto3."""

import sys
from github_utils import find_boto3_repos


def main():
    if len(sys.argv) < 2:
        print("Usage: python find-boto3.py <org>", file=sys.stderr)
        sys.exit(1)

    for repo in find_boto3_repos(sys.argv[1]):
        print(repo)


if __name__ == "__main__":
    main()
