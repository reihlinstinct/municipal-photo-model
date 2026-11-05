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
