# Municipal photo model

Public training-code preparation for human-reviewed municipal-photo classification and vehicle selection. Code and synthetic examples only. No private images, real labels, records or credentials.

This is a draft baseline, not a trained model. No upload or automatic municipal filing is implemented. See [design](docs/DESIGN.md), [structure](STRUCTURE.json) and the gated [notebook](notebooks/municipal_photo_baseline.ipynb).

Run synthetic tests with Python 3.12:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
python scripts/public_data_scan.py .
```

Optional local image preparation re-encodes pixels without metadata, leaves originals unchanged and does not anonymize plates/faces/location details. Dataset privacy and upload approval remain separate from this public code.
