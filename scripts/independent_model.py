"""Explicit binary checkpoint format for isolated class experiments."""
from pathlib import Path

LABELS = ('sidewalk_parking', 'red_white', 'crosswalk_obstruction')
FORMAT = 'independent-resnet18-binary-v1'


def build_model(*, pretrained=False):
    """Return a fresh model; never reuse parameters across classes."""
    import torch
    from torchvision import models
    weights = models.ResNet18_Weights.DEFAULT if pretrained else None
    model = models.resnet18(weights=weights)
    for parameter in model.parameters():
        parameter.requires_grad = False
    model.fc = torch.nn.Linear(model.fc.in_features, 1)
    for parameter in model.layer4.parameters():
        parameter.requires_grad = True
    return model


def load_checkpoint(path, *, device='cpu', expected_label=None):
    """Load only our explicit format without downloading pretrained weights."""
    import math
    import torch
    data = torch.load(Path(path), map_location=device, weights_only=True)
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise ValueError('Not an independent binary checkpoint')
    label = data.get('label')
    if label not in LABELS or (expected_label is not None and label != expected_label):
        raise ValueError('Checkpoint label mismatch')
    threshold = data.get('threshold')
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Invalid checkpoint threshold')
    model = build_model()
    model.load_state_dict(data['state_dict'], strict=True)
    return model.to(device).eval(), label, float(threshold)


# Section: Explicit experimental inference

def main():
    import argparse
    import json
    import torch
    from PIL import Image
    from torchvision import models
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint')
    parser.add_argument('images', nargs='+')
    args = parser.parse_args()
    model, label, threshold = load_checkpoint(args.checkpoint)
    tf = models.ResNet18_Weights.DEFAULT.transforms()
    for path in args.images:
        with Image.open(path) as image:
            x = tf(image.convert('RGB')).unsqueeze(0)
        with torch.no_grad():
            probability = float(model(x).sigmoid().item())
        print(json.dumps({'label': label, 'probability': probability,
                          'threshold': threshold, 'present': probability >= threshold}))


if __name__ == '__main__':
    main()
