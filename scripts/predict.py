#!/usr/bin/env python3
"""Run the municipal baseline checkpoint on one or more photos.

Informational predictions only. This never influences whether a photo is
filed as a violation; it attaches the model's per-class probability and a
thresholded present/absent call to each photo.

Usage:
    python scripts/predict.py CHECKPOINT IMAGE [IMAGE ...]

Example:
    python scripts/predict.py bounded-checkpoint.pt photo-1.jpg photo-2.jpg

Output: one JSON object per image on stdout, e.g.
    {"image": "photo-1.jpg", "predictions": {"sidewalk_parking": {"probability": 0.91, "present": true}, ...}, "thresholds": {...}}

Requirements: torch + torchvision (CPU wheels are fine) and Pillow:
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

Model: ResNet18 (frozen backbone) with a 3-way sigmoid head, trained on the
102-image reviewed pilot set. Per-class decision thresholds were picked by
F1 on the validation split and are embedded below (same values as reported
in bounded-metrics.json). Test set was tiny (11/5/1 positives), so treat
confidences as rough signals, not calibrated probabilities.
"""
import argparse
import json
import sys

LABELS = ['sidewalk_parking', 'red_white', 'crosswalk_obstruction']
THRESHOLDS = {'sidewalk_parking': 0.35, 'red_white': 0.30, 'crosswalk_obstruction': 0.90}

# ResNet18_Weights.DEFAULT.transforms() equivalent, written out so the script
# never needs network access for preprocessing config.
RESIZE_SIZE = 256
CROP_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def build_model(checkpoint_path, device):
    import torch
    from torchvision import models
    model = models.resnet18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, len(LABELS))
    state = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.to(device).eval()
    return model


def preprocess(path):
    from PIL import Image
    from torchvision import transforms
    tf = transforms.Compose([
        transforms.Resize(RESIZE_SIZE),
        transforms.CenterCrop(CROP_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    with Image.open(path) as im:
        return tf(im.convert('RGB'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('checkpoint', help='Path to bounded-checkpoint.pt')
    parser.add_argument('images', nargs='+', help='Photo paths to score')
    args = parser.parse_args()

    import torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = build_model(args.checkpoint, device)
    for path in args.images:
        try:
            x = preprocess(path).unsqueeze(0).to(device)
            with torch.no_grad():
                probs = model(x).sigmoid().cpu().numpy()[0]
            predictions = {
                label: {'probability': round(float(probs[i]), 4),
                        'present': bool(probs[i] >= THRESHOLDS[label])}
                for i, label in enumerate(LABELS)
            }
            print(json.dumps({'image': path, 'predictions': predictions,
                              'thresholds': THRESHOLDS, 'device': device}), flush=True)
        except Exception as exc:
            print(json.dumps({'image': path, 'error': str(exc)}), flush=True)


if __name__ == '__main__':
    sys.exit(main())
