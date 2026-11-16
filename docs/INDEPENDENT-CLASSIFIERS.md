# Independent classifiers experiment

Tracks #43. This is an opt-in research path, not a production model switch.

Each label gets its own ResNet18 instance, binary head, optimizer and BatchNorm
buffers. Only that class's known training labels are used. Each process starts
from ImageNet weights and the same seed. Layer4 and the head train; earlier
layers and all BatchNorm statistics remain frozen. No class can update another
class's backbone. This changes both supervision and architecture; a single run
cannot establish which change caused a score difference.

## Run

Use Python 3.11+, torch, torchvision, Pillow, numpy and scikit-learn in a private
GPU environment. The entry point refuses CPU training and runs one class at a
time through the existing process-tree watchdog. There are at most 100 steps,
12 epochs and 45 minutes per class (135 minutes maximum for three classes).
The caller must use free compute only; the scripts do not provision cloud jobs.

```
python scripts/train_independent.py --root PRIVATE_ROOT --manifest manifest.reviewed.json
```

The manifest must have train, val and test rows, image_sha256, group_id,
label_state and review_status. Unknown labels are excluded independently for
each class, not converted to negatives. Images must resolve inside the dataset
root. SHA/group cross-split collisions fail closed. Image-level review may use
approved_image_level_agent; the historical approved_image_level_human enum is
also accepted for compatibility and does not establish actual human authorship.
Retain accurate reviewer provenance in private manifests.

Outputs are three independent binary checkpoints and an aggregate metrics file.
The new format records architecture, label, threshold, seed and step count.
Legacy 3-output checkpoints are rejected by the new loader. Legacy scripts are
unchanged. Outputs contain weights and aggregate metrics, never image paths or
transcriptions. Keep real data and checkpoints private.

## Evaluation and promotion

Thresholds maximize validation F1 on the fixed 0.10 to 0.90 grid (0.05 step),
with the higher threshold winning ties. Every class needs positive and negative
examples in train and validation; otherwise stop rather than invent a threshold.
Test results include precision, recall, F1 and known/positive counts. A separate
frozen expanded test must be evaluated after training with those same thresholds.
No test-driven threshold tuning and no automatic promotion. Frozen tests reused
across experiments are development benchmarks, not an untouched final test.

Compare all three classes against the champion on both frozen benchmarks. A
crosswalk gain cannot silently compensate for regressions on other classes.
Architecture alone will not fix ambiguous labels or missing positive examples.
CI, independent review at the exact head and formal owner Approve gate merging.
