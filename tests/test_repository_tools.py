"""Tests for repository-only tooling; no inference/model downloads."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
c=load('check_repo');runner=load('run_checks')

class RepositoryToolTests(unittest.TestCase):
    def test_private_paths_blocked(self):
        for path in ['.env','ASR_SETTINGS.bat','models/model.onnx','recordings/take.wav','user-data/note.txt','x.sqlite3-wal','完整笔记.txt','cookies.txt','Cookies.json','youtube-cookies.txt']:
            self.assertIsNotNone(c.unsafe_path(path),path)
    def test_source_templates_allowed(self):
        for path in ['ASR_SETTINGS.example.bat','extension/options.html','docs/assets/compact-panel.png','.env.example']:
            self.assertIsNone(c.unsafe_path(path),path)
    def test_model_extension_blocked(self):
        self.assertIsNotNone(c.unsafe_path('large.gguf'))
    def test_batch_requires_ascii_and_crlf(self):
        self.assertTrue(c.inspect_bytes('x.bat','echo 中文\n'.encode()))
        self.assertEqual(c.inspect_bytes('x.bat',b'@echo off\r\n'),[])
    def test_git_index_lf_permitted(self):
        self.assertEqual(c.inspect_bytes('x.bat',b'@echo off\n',staged=True),[])
    def test_escaped_cmd_quotes_rejected(self):
        self.assertTrue(c.inspect_bytes('x.bat',b'cd \\"x\\"\r\n'))
    def test_secret_redacted(self):
        token='ghp_'+'z'*36
        errors=c.inspect_bytes('example.py',token.encode())
        self.assertTrue(errors);self.assertNotIn(token,' '.join(errors))
    def test_no_false_secret_on_placeholder(self):
        self.assertEqual(c.inspect_bytes('example.md',b'API Key: leave blank'),[])
    def test_missing_dependency_rejected(self):
        self.assertTrue(c.validate_backlog([{'id':'a','status':'todo','depends_on':['b']}],[]))
    def test_cycles_rejected(self):
        tasks=[{'id':'a','status':'todo','depends_on':['b']},{'id':'b','status':'todo','depends_on':['a']}]
        self.assertIn('task dependency cycle',c.validate_backlog(tasks,[]))
    def test_valid_plan_accepted(self):
        self.assertEqual(c.validate_backlog([{'id':'a','status':'todo','acceptance':['A1']}],[{'id':'A1'}]),[])
    def test_unit_runner_does_not_install(self):
        commands=runner.plan('unit')
        self.assertGreaterEqual(len(commands),5)
        self.assertTrue(any('run_js_tests.cjs' in ' '.join(cmd) for _,cmd in commands))
        self.assertFalse(any('pip' in cmd or 'install' in cmd for _,cmd in commands))
    def test_browser_is_explicit(self):
        self.assertFalse(any('browser_' in ' '.join(cmd) for _,cmd in runner.plan('unit')))
        self.assertTrue(any('browser_' in ' '.join(cmd) for _,cmd in runner.plan('browser')))
    def test_baseline_inventory_well_formed(self):
        import json,re
        rows=json.loads((ROOT/'qa/baseline-source-sha256.json').read_text())['files']
        self.assertEqual(len(rows),len({x['path'] for x in rows}))
        for row in rows:
            self.assertRegex(row['sha256'],r'^[a-f0-9]{64}$')
            self.assertTrue((ROOT/row['path']).is_file())

if __name__=='__main__': unittest.main()
