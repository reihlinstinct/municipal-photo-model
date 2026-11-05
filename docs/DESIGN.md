# Municipal photo model, design first

Public code, synthetic examples only. Images, manifests, labels and evidence supplied by a person stay outside this repository. No upload or training is performed by setup or CI.

## Targets
- Non-exclusive visual labels: sidewalk parking, red-white/no-stopping, crosswalk obstruction.
- Municipality classification from verified source-to-image associations, with submitted code separate from the city's assigned label.
- Offending-vehicle bounding box and visible plate transcription, preserving leading zeros. Begin with an existing OCR reader; registry/report strings are review hints, not proof of visible digits.
- Optional make/model/colour only with reviewed evidence.

No enforcement, fine, closure or effectiveness labels. No legal verdict or automatic report filing.

## Provenance and review
All source labels begin as candidates. Uncertain mappings and incomplete digits stay held. A crossing mentioned in text but outside the image is not automatically a visible crossing label. Background vehicles are not automatically the target vehicle. Municipality codes can be shared across category paths, and label vocabularies can differ from filed codes. Retain explicit ambiguity until reviewed.

The local manifest builder creates conservative transitive photo/street grouping. It intentionally over-groups; whole-location/event review and perceptual duplicate review are still required. Never randomly split related captures across train and test. Missing source grouping information is held. Do not derive negative labels from absent annotations.

## Privacy and data boundary
No original filenames, precise times, GPS/EXIF, addresses, case references, messages, report records, contacts, personal IDs, credentials or source evidence enter this repository. Public fixtures must be synthetic and clearly labelled. Private data needs a separate review and publication decision. Metadata stripping is not anonymization: plates, faces and locations may remain in pixels. No upload capability or credentials are included.

## Baseline
Draft notebook has a frozen pretrained visual backbone and three sigmoid outputs. Before training it requires reviewed present/absent visual labels, target boxes and group-disjoint train/validation/test. It refuses absent positive/negative examples. Validation selects thresholds; test is held out. It has no completed city-classification, OCR, vehicle-detector or type head; those are explicit next work rather than implied functionality.

## Validation
Synthetic unit tests cover grouping, missing metadata, multi-label candidates, no original overwrite, metadata removal and notebook syntax/review gates. CI runs in a fixed Python image and installs pinned dependencies. Public CI uses no private data or secrets. Container success, trained quality and annotation completion must be reported separately.
