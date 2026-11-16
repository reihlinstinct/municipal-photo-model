"""One bounded binary-class training process. No provisioning or uploads."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import random
import sys

# Isolated Python excludes the script directory. Import only these trusted siblings.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from independent_model import LABELS, FORMAT, build_model
from independent_data import read_manifest, class_rows, select_threshold, binary_metrics

SEED = 329
MAX_STEPS = 100


def run(args, emit):
    import torch
    if not torch.cuda.is_available():
        raise ValueError('CUDA required')
    progress = 0

    def setup():
        nonlocal progress
        progress += 1
        emit(heartbeat='setup', progress=progress)

    setup()
    rows = read_manifest(args.root, args.manifest, setup)
    splits = {s: class_rows(rows, args.label, s) for s in ('train', 'val', 'test')}
    for split in ('train', 'val'):
        states = {r['label_state'][args.label] for r in splits[split]}
        if states != {'present', 'absent'}:
            raise ValueError('Train/validation need both classes')
    if not splits['test']:
        raise ValueError('No known test labels')
    random.seed(SEED)
    torch.manual_seed(SEED)
    from torch import nn
    from torch.utils.data import Dataset, DataLoader
    from torchvision import models, transforms
    from PIL import Image
    eval_tf = models.ResNet18_Weights.DEFAULT.transforms()
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(.6, 1.)),
        transforms.RandomHorizontalFlip(), transforms.ColorJitter(.2, .2, .2, .05),
        transforms.RandomRotation(7), transforms.ToTensor(),
        transforms.Normalize([.485, .456, .406], [.229, .224, .225]),
    ])

    class Photos(Dataset):
        def __init__(self, split):
            self.rows = splits[split]
            self.tf = train_tf if split == 'train' else eval_tf

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            row = self.rows[index]
            with Image.open(Path(args.root) / row['image']) as image:
                x = self.tf(image.convert('RGB'))
            return x, float(row['label_state'][args.label] == 'present')

    datasets = {s: Photos(s) for s in splits}
    setup()
    model = build_model(pretrained=True).to('cuda')
    setup()
    pos = sum(r['label_state'][args.label] == 'present' for r in splits['train'])
    neg = len(splits['train']) - pos
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([neg / pos], device='cuda'))
    optimizer = torch.optim.Adam([
        {'params': model.fc.parameters(), 'lr': 1e-3},
        {'params': model.layer4.parameters(), 'lr': 1e-4},
    ])
    loader = DataLoader(datasets['train'], batch_size=32, shuffle=True, num_workers=0)
    emit(stage='train')
    steps = 0
    for _ in range(12):
        model.train()
        for module in model.modules():
            if isinstance(module, nn.BatchNorm2d):
                module.eval()
        for x, y in loader:
            optimizer.zero_grad()
            loss = loss_fn(model(x.to('cuda')).flatten(), y.float().to('cuda'))
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite loss')
            loss.backward()
            optimizer.step()
            steps += 1
            emit(step=steps, loss=float(loss.detach().cpu()))
            if steps >= MAX_STEPS:
                break
        if steps >= MAX_STEPS:
            break
    emit(stage='evaluate')
    eval_progress = 0

    @torch.no_grad()
    def predict(split):
        nonlocal eval_progress
        model.eval()
        probabilities, truth = [], []
        for x, y in DataLoader(datasets[split], batch_size=16, num_workers=0):
            probabilities.extend(model(x.to('cuda')).flatten().sigmoid().cpu().tolist())
            truth.extend(int(v) for v in y.tolist())
            eval_progress += 1
            emit(heartbeat='evaluate', progress=eval_progress)
        return truth, probabilities

    vy, vp = predict('val')
    threshold = select_threshold(vy, vp)
    ty, tp = predict('test')
    result = {'label': args.label, 'seed': SEED, 'steps': steps, 'threshold': threshold,
              'train_known': len(splits['train']), 'val_known': len(splits['val']),
              'test': binary_metrics(ty, tp, threshold)}
    output = Path(args.output)
    # Only publish a checkpoint with the threshold after successful evaluation.
    torch.save({'format': FORMAT, 'label': args.label, 'threshold': threshold,
                'seed': SEED, 'steps': steps, 'state_dict': model.cpu().state_dict()},
               output / (args.label + '.pt'))
    (output / (args.label + '.json')).write_text(json.dumps(result, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--label', choices=LABELS, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    protocol = sys.stdout

    def emit(**event):
        print(json.dumps(event, allow_nan=False), file=protocol, flush=True)

    try:
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            run(args, emit)
    except Exception:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
