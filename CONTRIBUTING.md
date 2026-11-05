# Contributing

Use an issue and design before code, then a branch and pull request. Keep documentation in English. Never commit real photos, plates, cases, private data or notebook outputs. Use symbolic placeholders rather than personal example values.

Python 3.11 or newer is required. Install requirements-test.txt, then run unittest discovery, scripts/check_structure.py and scripts/public_data_scan.py from the repository root. CI runs these checks inside a pinned Python container. Independent review and green CI at the exact head are required before squash merge. Do not claim an unexecuted model is trained.
