import importlib.util,tempfile,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('manifest',Path(__file__).parents[1]/'scripts/municipal_photo_manifest.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ManifestTests(unittest.TestCase):
    def test_multi_label_no_false_negatives(self):
        r=m.build([{'source_id':'synthetic-a','street':'synthetic street','photo_sha256':'a'*64,'category':'red_white_crosswalk'}])[0]
        self.assertEqual(r['candidate_labels'],['red_white','crosswalk_obstruction'])
        self.assertEqual(set(r['label_state'].values()),{'unknown'});self.assertFalse(r['upload_approved']);self.assertEqual(r['split'],'unassigned')
    def test_transitive_group_leakage_control(self):
        rs=[{'source_id':'a','street':'A','photo_sha256':'1'}, {'source_id':'b','street':'A','photo_sha256':'2'}, {'source_id':'c','street':'B','photo_sha256':'2'}, {'source_id':'d','street':'C','photo_sha256':'3'}]
        a,b,c,d=m.build(rs);self.assertEqual(a['group_id'],b['group_id']);self.assertEqual(b['group_id'],c['group_id']);self.assertNotEqual(c['group_id'],d['group_id'])
    def test_missing_metadata_held(self):
        r=m.build([{'source_id':'synthetic','category':'sidewalk_parking'}])[0]
        self.assertEqual(r['review_status'],'held_missing_group_data')
    def test_strip_preserves_original_and_drops_metadata(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.jpg';target=Path(d)/'clean.jpg';im=Image.new('RGB',(40,20),'red');exif=Image.Exif();exif[270]='synthetic private metadata';im.save(source,exif=exif);before=source.read_bytes();m.strip_metadata(source,target)
            with Image.open(target) as clean:self.assertFalse(clean.getexif());self.assertNotIn('comment',clean.info);self.assertEqual(clean.size,(40,20))
            self.assertEqual(source.read_bytes(),before)
            with self.assertRaises(ValueError):m.strip_metadata(source,source)
            with self.assertRaises(ValueError):m.strip_metadata(source,target)

class NotebookTests(unittest.TestCase):
    def test_notebook_syntax_and_review_gate(self):
        import json
        nb=json.loads((Path(__file__).parents[1]/'notebooks/municipal_photo_baseline.ipynb').read_text())
        code='\n'.join(''.join(x['source']) for x in nb['cells'] if x['cell_type']=='code')
        compile(code,'notebook','exec')
        self.assertIn('approved_visual_event_and_target',code)
        self.assertIn('Group leakage',code)
        self.assertNotIn('kaggle.api',code)

if __name__=='__main__':unittest.main()
