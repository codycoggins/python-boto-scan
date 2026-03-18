# python-boto-scan

Scan a GitHub org (or user account) to find repositories that use **boto3** and flag any running on **Python 3.9 or earlier** — the last version boto3 will support before dropping it in April 2026.

## Background

boto3 is dropping Python 3.9 support in April 2026. If your org has many repos, manually checking each one is tedious. These scripts automate the audit:

1. Find every repo that references boto3
2. Detect the Python version each repo targets
3. Categorize boto3 repos as **needs remediation**, **unknown version**, or **safe**

## Requirements

- Python 3.11+
- [`gh` CLI](https://cli.github.com/) — authenticated (`gh auth login`)

## Setup

```bash
bash setup.sh
source venv/bin/activate
```

## Scripts

### 1. `find-boto3.py` — Find repos using boto3

```bash
python find-boto3.py <org>
```

Uses GitHub code search to find all non-archived, non-fork repos in the org that reference boto3. Outputs one `owner/repo` per line.

```
myorg/data-pipeline
myorg/batch-processor
```

### 2. `repo-py-versions.py` — Detect Python version per repo

```bash
python repo-py-versions.py <org>
```

Scans every non-archived, non-fork repo and reports its Python version. Detection checks these files in priority order:

| Priority | File | Method |
|----------|------|--------|
| 1 | `Dockerfile*` | `FROM python:X.Y` |
| 2 | `pyproject.toml` | `requires-python` or Poetry `python` dependency |
| 3 | `.python-version` | direct version string |
| 4 | `runtime.txt` | strips `python-` prefix |
| 5 | `setup.cfg` | `python_requires` |
| 6 | `setup.py` | `python_requires` |

Output is tab-separated:

```
myorg/data-pipeline     python    3.12
myorg/old-service       python    3.9
myorg/frontend          not-python
myorg/undeclared        python    unknown
```

### 3. `needs-py-boto3-remediation.py` — Flag at-risk repos

```bash
# Full scan (runs boto3 search internally)
python needs-py-boto3-remediation.py <org>

# Faster: reuse output from find-boto3.py
python find-boto3.py <org> > boto3_repos.txt
python needs-py-boto3-remediation.py <org> --boto3-list boto3_repos.txt
```

Intersects the boto3 repo list with Python version detection and categorizes each repo:

```
=== NEEDS REMEDIATION (boto3 + Python <= 3.9) ===
  myorg/old-service    python 3.9

=== UNKNOWN VERSION (boto3 found, Python version undetectable) ===
  myorg/undeclared

=== SAFE (boto3 + Python >= 3.10) ===
  myorg/data-pipeline  python 3.12

Summary: 1 need remediation, 1 unknown, 1 safe
```

## Notes

- **Private repos are included** — the `gh` CLI uses your authenticated token automatically.
- **Rate limits**: file fetching uses the GitHub core API (5,000 req/hr). A 0.1s delay between file fetches keeps usage well within limits. The code search in `find-boto3.py` uses a single query against the search API (30 req/min limit).
- Forks and archived repos are excluded from all scans.
