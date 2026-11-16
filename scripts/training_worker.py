"""Internal worker: only launched by train_bounded.py, never an upload tool."""
from __future__ import annotations
import argparse
import contextlib
import json
import os
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")

def run(args, emit):
    import torch
    if not torch.cuda.is_available():
        raise ValueError('CUDA required')
    emit(heartbeat='setup', progress=1)
    setup_progress = 1
    from pathlib import Path
    import json, hashlib, random
    ROOT = Path(args.root)
    manifest = json.loads((ROOT / 'manifest.reviewed.json').read_text())
    LABELS = ['sidewalk_parking', 'red_white', 'crosswalk_obstruction']
    if not (manifest):
        raise ValueError('No reviewed manifest')
    for row in manifest:
        if not (row['review_status'] == 'approved_visual_event_and_target'):
            raise ValueError('Review images/events/target boxes first')
        if not (row['split'] in {'train','val','test'}):
            raise ValueError('Review or data validation failed')
        if not (row['target_vehicle_box'] is not None):
            raise ValueError('Review or data validation failed')
        if not (all(row['label_state'][label] in {'present','absent'} for label in LABELS)):
            raise ValueError('Review or data validation failed')
        setup_progress += 1
        emit(heartbeat='setup', progress=setup_progress)
        path = ROOT / row['image']
        if not (hashlib.sha256(path.read_bytes()).hexdigest() == row['image_sha256']):
            raise ValueError('Review or data validation failed')
    # Whole-location/event groups never cross partitions.
    seen={}
    for row in manifest:
        if not (seen.setdefault(row['group_id'], row['split']) == row['split']):
            raise ValueError('Group leakage')
    if not ({r['split'] for r in manifest} == {'train','val','test'}):
        raise ValueError('Review or data validation failed')
    
    import torch
    from torch import nn
    from torch.utils.data import Dataset, DataLoader
    from torchvision import models, transforms
    from PIL import Image
    random.seed(329); torch.manual_seed(329)
    device = 'cuda'
    transform = models.ResNet18_Weights.DEFAULT.transforms()
    class Photos(Dataset):
        def __init__(self, split): self.rows=[r for r in manifest if r['split']==split]
        def __len__(self): return len(self.rows)
        def __getitem__(self,i):
            r=self.rows[i]
            with Image.open(ROOT/r['image']) as image: x=transform(image.convert('RGB'))
            y=torch.tensor([r['label_state'][k]=='present' for k in LABELS],dtype=torch.float32)
            return x,y
    train=Photos('train'); val=Photos('val'); test=Photos('test')
    if not (min(len(train),len(val),len(test))>0):
        raise ValueError('Review or data validation failed')
    # Weight download occurs only during separately approved notebook execution.
    setup_progress += 1
    emit(heartbeat='setup', progress=setup_progress)
    model=models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    for p in model.parameters(): p.requires_grad=False
    model.fc=nn.Linear(model.fc.in_features,len(LABELS));model.to(device)
    y=torch.stack([train[i][1] for i in range(len(train))]); pos=y.sum(0)
    if not (torch.all(pos>0) and torch.all(pos<len(train))):
        raise ValueError('Need positive and negative examples per class')
    loss_fn=nn.BCEWithLogitsLoss(pos_weight=((len(train)-pos)/pos).to(device))
    optimizer=torch.optim.Adam(model.fc.parameters(),lr=1e-3)
    train_loader=DataLoader(train,batch_size=16,shuffle=True,num_workers=0)
    emit(stage="train")
    steps = 0
    for epoch in range(5):
        model.train();model.bn1.eval() # Frozen backbone statistics should not update.
        for module in model.modules():
            if isinstance(module, nn.BatchNorm2d): module.eval()
        for x,y in train_loader:
            if steps >= 100: break
            optimizer.zero_grad();loss=loss_fn(model(x.to(device)),y.to(device))
            if not (torch.isfinite(loss)):
                raise ValueError('Nonfinite loss')
            loss.backward();optimizer.step()
            steps += 1
            emit(step=steps, loss=float(loss.detach().cpu()))
        torch.save(model.state_dict(), 'bounded-checkpoint.pt')
        if steps >= 100: break
    emit(stage="evaluate")
    
    from sklearn.metrics import precision_recall_fscore_support, average_precision_score
    import numpy as np
    evaluation_progress = 0
    @torch.no_grad()
    def predict(ds):
        nonlocal evaluation_progress
        model.eval();probs=[];truth=[]
        for x,y in DataLoader(ds,batch_size=16,num_workers=0):
            evaluation_progress += 1
            emit(heartbeat='evaluate', progress=evaluation_progress)
            probs.append(model(x.to(device)).sigmoid().cpu().numpy());truth.append(y.numpy())
        return np.concatenate(probs),np.concatenate(truth)
    vp,vy=predict(val)
    thresholds=[]
    for i in range(len(LABELS)):
        scores=[]
        for threshold in np.arange(.1,.91,.05):
            _,_,f,_=precision_recall_fscore_support(vy[:,i],vp[:,i]>=threshold,average='binary',zero_division=0)
            scores.append((f,threshold))
        thresholds.append(max(scores)[1])
    tp,ty=predict(test)
    p,r,f,s=precision_recall_fscore_support(ty,tp>=np.array(thresholds),average=None,zero_division=0)
    metrics = {}
    for i,label in enumerate(LABELS):
        metrics[label] = dict(precision=float(p[i]),recall=float(r[i]),f1=float(f[i]),support=int(s[i]),threshold=float(thresholds[i]))
    # Report group counts and exclusions, not only image counts. No legal-violation accuracy claim.
    
    Path('bounded-metrics.json').write_text(json.dumps(metrics))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
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
