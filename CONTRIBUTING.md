# Contributing

Use an issue and design before code, then a branch and pull request. Keep documentation in English. Never commit real photos, plates, cases, private data or notebook outputs. Use symbolic placeholders rather than personal example values.

Python 3.11 or newer is required. Install requirements-test.txt, then run unittest discovery, scripts/check_structure.py and scripts/public_data_scan.py from the repository root. CI runs these checks inside a pinned Python container. Independent review and green CI at the exact head are required before squash merge. Do not claim an unexecuted model is trained.

## File placement (enforced)

Decide where a file lives BEFORE creating it. The contract in `.repo-layout.yml` lists the allowed top-level directories, the file types permitted in each, and the required community-standards files; `python3 tools/check_repo_layout.py` enforces it in CI. A new kind of file means updating the contract in the same PR.

## In-file code layout

Follow the shared code-layout standard in collaboration-docs docs/CODE-LAYOUT.md.
Order code by reading flow, put entry points before their helpers, and use
marked section headers for longer files. Source files have a 400-line cap;
test files have a 600-line cap and should split by topic above it.
