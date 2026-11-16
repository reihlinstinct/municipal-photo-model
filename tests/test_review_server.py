"""All images, metadata and plate-like text are made at runtime, outside the repo."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from PIL import Image

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('review_server', ROOT / 'scripts/review_server.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'data'
        self.root.mkdir()
        self.candidates = self.base / 'candidates.json'
        self.rows = []
        for i in range(4):
            file = self.root / f'synthetic-{i}.png'
            Image.new('RGB', (100, 80), (i * 40, 20, 50)).save(file)
            self.rows.append(dict(local_source_id=f'event-{i}', image=file.name,
                image_sha256=m.digest(file), group_id=f'group-{i}', candidate_labels=[],
                label_state={k: 'unknown' for k in m.LABELS}, review_status='needs_visual_and_event_review',
                upload_approved=False))
        self.write_candidates()
        self.store = self.create_store()

    def tearDown(self):
        self.temp.cleanup()

    def write_candidates(self):
        self.candidates.write_text(json.dumps(self.rows))

    def create_store(self):
        return m.ReviewStore(self.root, self.candidates, self.base / 'work')

    def review(self, i=0):
        return dict(label_state={k: 'present' if i == 0 else 'absent' for k in m.LABELS},
            target_vehicle_box=[1, 2, 99, 79], plate_box=[10, 50, 50, 60],
            plate_text=''.join(['12', '345', '67']), plate_status='readable',
            municipal_category='synthetic municipality category', split=['train', 'train', 'val', 'test'][i],
            reviewer='Synthetic human', event_checked=True, visual_checked=True, notes='', exclusion_reason='')

    def save(self, i=0, decision='approved', review=None):
        return self.store.save(dict(revision=self.store.state['revision'], index=i,
            review=review or self.review(i), decision=decision))

    def approve_all(self):
        for i in range(4):
            self.save(i)

    def test_candidates_remain_unreviewed(self):
        self.assertEqual(self.store.state['reviews'], {})
        self.assertFalse((self.base / 'work/manifest.reviewed.json').exists())
        with self.assertRaises(ValueError):
            self.store.export()

    def test_resume_and_optimistic_lock(self):
        self.save(decision='draft')
        self.assertEqual(self.create_store().state, self.store.state)
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.store.save(dict(revision=0, index=0, review=self.review(), decision='approved'))
        self.assertEqual(self.store.state['revision'], 1)

    def test_complete_export_compatible_with_worker(self):
        self.approve_all()
        result = self.store.export()
        self.assertEqual(len(result), 4)
        self.assertEqual({r['split'] for r in result}, {'train', 'val', 'test'})
        for row in result:
            self.assertEqual(row['review_status'], 'approved_visual_event_and_target')
            self.assertEqual(row['image_sha256'], m.digest(self.root / row['image']))
            self.assertEqual(row['box_format'], 'xyxy_pixels')
            self.assertFalse(row['upload_approved'])
        self.assertTrue((self.base / 'work/review-audit.json').is_file())
        self.save(decision='draft')
        self.assertFalse((self.base / 'work/manifest.reviewed.json').exists())

    def test_no_auto_approval_or_missing_event_evidence(self):
        for key, value in [('reviewer',''), ('event_checked',False), ('visual_checked',False),
                           ('municipal_category',''), ('target_vehicle_box',None), ('split','unassigned')]:
            review=self.review(); review[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.save(review=review)
        review=self.review(); review['label_state'][m.LABELS[0]]='unknown'
        with self.assertRaises(ValueError):
            self.save(review=review)

    def test_box_geometry(self):
        for box in [[], [0,0,0,5], [-1,0,20,20], [0,0,101,80], [0,0,1,float('nan')], [0,0,1,float('inf')], [False,0,2,3]]:
            review=self.review(); review['target_vehicle_box']=box
            with self.subTest(box=box), self.assertRaises(ValueError):
                self.save(review=review)
        review=self.review();review['plate_box']=[0,0,10,10]
        with self.assertRaisesRegex(ValueError, 'inside'):
            self.save(review=review)

    def test_plate_states(self):
        for status in ['unknown','unreadable','not_visible']:
            review=self.review();review['plate_status']=status
            with self.assertRaises(ValueError):
                self.save(review=review)
        review=self.review();review.update(plate_status='not_visible',plate_box=None,plate_text='')
        self.save(review=review)
        review=self.review();review.update(plate_status='unreadable',plate_text='')
        self.save(review=review)

    def test_exclusions_require_reason(self):
        with self.assertRaises(ValueError):
            self.save(decision='excluded')
        review=self.review();review['exclusion_reason']='Synthetic occlusion'
        self.save(decision='excluded',review=review)

    def test_changed_image_blocks_export(self):
        self.approve_all()
        Image.new('RGB',(100,80),'blue').save(self.root / self.rows[0]['image'])
        with self.assertRaisesRegex(ValueError,'changed'):
            self.store.export()

    def test_group_leakage_and_no_train_positives(self):
        self.approve_all()
        self.store.rows[2]['group_id']=self.store.rows[0]['group_id']
        with self.assertRaisesRegex(ValueError,'leakage'):
            self.store.export()
        self.store.rows[2]['group_id']='group-2'
        review=self.review(0);review['label_state']={k:'absent' for k in m.LABELS}
        self.save(0,review=review)
        with self.assertRaisesRegex(ValueError,'positive and negative'):
            self.store.export()

    def test_traversal_absolute_symlink_and_bad_hash(self):
        for name in ['../outside.png', '/outside.png']:
            with self.assertRaises(ValueError):
                m.image_path(self.root,name)
        outside=self.base / 'outside.png';Image.new('RGB',(1,1)).save(outside)
        (self.root / 'link.png').symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            m.image_path(self.root,'link.png')
        self.rows[0]['image_sha256']='a'*64;self.write_candidates()
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            self.create_store()

    def test_schema_and_group_metadata_fail_closed(self):
        for missing in ['group_id','label_state','candidate_labels','review_status']:
            original=copy.deepcopy(self.rows)
            self.rows[0].pop(missing);self.write_candidates()
            with self.assertRaises(ValueError):
                self.create_store()
            self.rows=original
        self.rows[0]['review_status']='held_missing_group_data';self.write_candidates();self.store=self.create_store()
        with self.assertRaisesRegex(ValueError,'group data'):
            self.save()

    def test_identical_photos_same_group(self):
        self.rows[1]['image_sha256']=self.rows[0]['image_sha256']
        (self.root / self.rows[1]['image']).write_bytes((self.root / self.rows[0]['image']).read_bytes())
        self.write_candidates()
        with self.assertRaisesRegex(ValueError,'Identical'):
            self.create_store()

    def test_actual_pilot_schema_and_candidate_plate_privacy(self):
        for row in self.rows:
            row.pop('local_source_id')
            row['city_label']='synthetic city category'
            row['plate_text_candidate']='NEVER-SURFACE'
            row['city_code']=None
        self.write_candidates();self.store=self.create_store()
        self.assertNotIn('NEVER-SURFACE',json.dumps(self.store.data()))
        self.approve_all()
        self.assertNotIn('plate_text_candidate',json.dumps(self.store.export()))
        review=self.review();review['plate_text_candidate']='NEVER-SURFACE'
        with self.assertRaisesRegex(ValueError,'Unexpected'):
            self.save(review=review)

    def test_changed_candidates_block_resume(self):
        self.save(decision='draft');self.rows[0]['candidate_labels']=[m.LABELS[0]];self.write_candidates()
        with self.assertRaisesRegex(ValueError,'different candidates'):
            self.create_store()

    def test_data_must_not_live_in_code_tree(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            m.ReviewStore(self.root,self.candidates,ROOT / 'work')

    def test_http_auth_no_store_and_no_arbitrary_files(self):
        server=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler)
        server.token='synthetic-session';server.store=self.store
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(HTTPError) as exc:
                urlopen(base+'/api/data')
            self.assertEqual(exc.exception.code,401)
            request=Request(base+'/api/data',headers={'Authorization':'Bearer '+server.token})
            with urlopen(request) as response:
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
                self.assertEqual(len(json.load(response)['rows']),4)
            for path in ['/api/image/-1','/api/image/100','/api/image/../../outside.png','/review-state.json']:
                with self.assertRaises(HTTPError) as exc:
                    urlopen(Request(base+path,headers={'Authorization':'Bearer '+server.token}))
                self.assertEqual(exc.exception.code,404)
            with self.assertRaises(HTTPError) as exc:
                urlopen(Request(base+'/api/save',data=b'{}',method='POST'))
            self.assertEqual(exc.exception.code,401)
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__ == '__main__':
    unittest.main()
