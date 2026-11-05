"""Local-only candidate manifest. No network, training or export authority."""
from __future__ import annotations
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")
import hashlib
import json
from pathlib import Path

LABELS = ('sidewalk_parking','red_white','crosswalk_obstruction')

def candidate_labels(category: str) -> list[str]:
    return {'sidewalk_parking':['sidewalk_parking'],'sidewalk':['sidewalk_parking'],
            'red_white_curb':['red_white'],'red_white_curb_parking':['red_white'],
            'red_white_parking':['red_white'],'crosswalk_parking':['crosswalk_obstruction'],
            'crosswalk_obstruction':['crosswalk_obstruction'],
            'red_white_crosswalk':['red_white','crosswalk_obstruction']}.get(category,[])

def build(records: list[dict]) -> list[dict]:
    """Input is private inventory; output remains private, never an upload manifest."""
    parent=list(range(len(records)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b):parent[find(b)]=find(a)
    seen={}
    for i,r in enumerate(records):
        for kind,value in [('street',r.get('street')),('photo',r.get('photo_sha256'))]:
            if value:
                key=(kind,value)
                if key in seen:union(i,seen[key])
                else:seen[key]=i
    members={}
    for i,r in enumerate(records):members.setdefault(find(i),[]).append(r['source_id'])
    result=[]
    for i,r in enumerate(records):
        labels=candidate_labels(r.get('category',''))
        group=hashlib.sha256(json.dumps(sorted(members[find(i)]),separators=(',',':')).encode()).hexdigest()[:24]
        result.append({'local_source_id':r['source_id'],'candidate_labels':labels,
                       'label_state':{x:'unknown' for x in LABELS},'group_id':group,
                       'review_status':'held_missing_group_data' if not r.get('street') or not r.get('photo_sha256') else 'needs_visual_and_event_review',
                       'target_vehicle_box':None,'plate_box':None,'plate_text':None,
                       'split':'unassigned','upload_approved':False})
    return result

def strip_metadata(source: Path, target: Path) -> None:
    """Clean pixel-only RGB JPEG; originals unchanged. No redaction implied."""
    from PIL import Image,ImageOps
    if source.resolve()==target.resolve():raise ValueError('Refuse original overwrite')
    if target.exists():raise ValueError('Refuse existing output overwrite')
    with Image.open(source) as image:
        rgb=ImageOps.exif_transpose(image).convert('RGB')
        clean=Image.new('RGB',rgb.size);clean.paste(rgb)
        clean.save(target,'JPEG',quality=95)
