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

    def test_any_stage_progress_heartbeat(self):
        code = "import json,time; print(json.dumps({'heartbeat':'setup','progress':1})); time.sleep(.08); print(json.dumps({'stage':'train'})); print(json.dumps({'stage':'evaluate'})); print(json.dumps({'heartbeat':'evaluate','progress':1})); time.sleep(.08); print(json.dumps({'heartbeat':'evaluate','progress':2}))"
        self.assertEqual(m.supervise([sys.executable,'-u','-c',code], total_seconds=2, idle_seconds=.15), 'ok')

    def test_pure_step_cap(self):
        code = "import json; print(json.dumps({'stage':'train'})); [print(json.dumps({'step':i,'loss':.5})) for i in range(1,102)]"
        self.assertEqual(self.run_child(code), 'step_limit')

    def test_process_group_grandchild_killed(self):
        import tempfile, time, os
        with tempfile.TemporaryDirectory() as d:
            pidfile=Path(d)/'pid'
            child="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)']); open("+repr(str(pidfile))+",'w').write(str(p.pid)); time.sleep(20)"
            self.assertEqual(self.run_child(child), 'no_progress')
            pid=int(pidfile.read_text())
            # Killed descendants may briefly remain as zombies until reaped by init.
            for _ in range(50):
                stat=Path('/proc')/str(pid)/'stat'
                if not stat.exists() or stat.read_text().split()[2]=='Z': break
                time.sleep(.01)
            else: self.fail('Grandchild still running')

    def test_worker_cuda_gate_before_manifest_under_optimized_python(self):
        # Synthetic torch module proves CUDA check happens before any file lookup.
        worker=ROOT/'scripts/training_worker.py'
        code="import importlib.util,types,sys; sys.modules['torch']=types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda:False)); s=importlib.util.spec_from_file_location('w',"+repr(str(worker))+"); w=importlib.util.module_from_spec(s);s.loader.exec_module(w); w.run(types.SimpleNamespace(root='/missing-synthetic-root'),lambda **e:None)"
        result=subprocess.run([sys.executable,'-O','-c',code],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('CUDA required',result.stderr)
        self.assertNotIn('FileNotFoundError',result.stderr)

if __name__ == '__main__': unittest.main()
