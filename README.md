# Municipal photo model

Public training-code preparation for human-reviewed municipal-photo classification and vehicle selection. Code and synthetic examples only. No private images, real labels, records or credentials.

This is a draft baseline, not a trained model. No upload or automatic municipal filing is implemented. See [design](docs/DESIGN.md), [structure](STRUCTURE.json) and the gated [notebook](notebooks/municipal_photo_baseline.ipynb).

Requires Python 3.11 or newer (CI uses Python 3.12). No public service API is exposed.

Run synthetic tests:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
python scripts/check_structure.py .
python scripts/public_data_scan.py .
```

Optional local image preparation re-encodes pixels without metadata, leaves originals unchanged and does not anonymize plates/faces/location details. Dataset privacy and upload approval remain separate from this public code.

See [contributing](CONTRIBUTING.md), [security](SECURITY.md), [accessibility](ACCESSIBILITY.md), [conduct](CODE_OF_CONDUCT.md) and [MIT license](LICENSE). Structure rules enforce required root files and per-folder allow/forbid/required inventories in CI.

## Privacy scanner limits

The scanner deliberately fails closed. Space-separated numeric lists can resemble phone numbers and be flagged even when they are harmless (for example, a list of ports). Write number lists with commas. This is an accepted false positive, not evidence of private data. A passing scan still does not prove privacy: manual review is required, and unsupported secrets or personal text may evade pattern checks.

Bounded run CLI and API: see [run-safety design](docs/RUN-SAFETY.md). The notebook calls a separate supervised worker; no upload/run approval is inferred. Remote GPU session shutdown still needs external Stop/Cancel and verification.
