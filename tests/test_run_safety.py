import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('bounded', ROOT/'scripts/train_bounded.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class SupervisorTests(unittest.TestCase):
    def run_child(self, code, **kwargs):
        return m.supervise([sys.executable, '-u', '-c', code], total_seconds=2,
                           stage_seconds={'setup': 1, 'train': 1, 'evaluate': 1}, idle_seconds=.5, **kwargs)

    def test_success(self):
        self.assertEqual(self.run_child('import json; print(json.dumps({"stage":"train"})); print(json.dumps({"step":1,"loss":.5})); print(json.dumps({"stage":"evaluate"}))'), 'ok')

    def test_idle_kills(self):
        self.assertEqual(self.run_child('import time; time.sleep(10)'), 'no_progress')

    def test_setup_timeout(self):
        self.assertEqual(m.supervise([sys.executable,'-c','import time; time.sleep(10)'], total_seconds=2, stage_seconds={'setup':.1,'train':1,'evaluate':1}, idle_seconds=1), 'stage_timeout')

    def test_total_timeout(self):
        self.assertEqual(m.supervise([sys.executable,'-c','import time; time.sleep(10)'], total_seconds=.1, idle_seconds=1), 'total_timeout')

    def test_bad_worker_and_private_output_not_echoed(self):
        self.assertEqual(self.run_child('print("private-input-not-a-protocol-event")'), 'invalid_event')
        self.assertEqual(self.run_child('raise RuntimeError("synthetic")'), 'worker_failed')

    def test_stage_reset_forbidden(self):
        self.assertEqual(self.run_child('print(' + repr(json.dumps({'stage':'setup'})) + ')'), 'invalid_stage')

    def test_nonfinite_and_step_jump(self):
        for event, expected in [({'step':1,'loss':float('nan')},'nonfinite_loss'), ({'step':101,'loss':1},'step_limit')]:
            code='import json; print(json.dumps({"stage":"train"})); print('+repr(json.dumps(event))+')'
            self.assertEqual(self.run_child(code), expected)

    def test_budget_validation(self):
        with self.assertRaises(ValueError): m.supervise([], total_seconds=3000)

    def test_worker_and_notebook_contract(self):
        source=(ROOT/'scripts/training_worker.py').read_text()
        compile(source,'worker','exec')
        for value in ['CUDA required','range(5)','steps >= 100','torch.isfinite(loss)','approved_visual_event_and_target','Group leakage','emit(stage="evaluate")']:
            self.assertIn(value, source)
        nb=json.loads((ROOT/'notebooks/municipal_photo_baseline.ipynb').read_text())
        self.assertIn('timeout=2760',''.join(nb['cells'][1]['source']))

if __name__ == '__main__': unittest.main()
