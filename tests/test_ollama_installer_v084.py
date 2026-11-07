"""Ollama Qwen3-ASR installer tests; local fake HTTP only, never downloads weights."""
from __future__ import annotations
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from install_support import InstallFailure, MODEL_NAMES, OllamaClient, ensure_model, OLLAMA_ASR_DOWNLOADABLE
from test_installer_v081 import fake_ollama
import install_all


class QwenASRInstallerTests(unittest.TestCase):
    def test_one_click_install_plan_includes_asr_download(self):
        for profile in ('all', 'core', 'models'):
            self.assertIn('ollama_asr', [row['id'] for row in install_all.plan(profile, 'small')])
        self.assertIn('asr', MODEL_NAMES)
        self.assertEqual(MODEL_NAMES['asr'], 'frozenlab/qwen3-asr:1.7b')
        self.assertEqual(install_all.PROFILES['asr'], ['runtime', 'asr'])

    def test_new_model_pulls_once_via_local_ollama_http_then_verifies(self):
        with fake_ollama() as (client, state):
            result = ensure_model(client, MODEL_NAMES['asr'], sleep=lambda _: None)
            self.assertEqual(result['state'], 'installed')
            self.assertTrue(result['metadata_readable'])
            self.assertFalse(result['inference_tested'])
            self.assertEqual(state['pulls'], 1)
            self.assertEqual(next(body for path, body in state['bodies'] if path == '/api/pull')['model'], MODEL_NAMES['asr'])

    def test_existing_asr_skips_pull(self):
        with fake_ollama() as (client, state):
            state['models'].add(MODEL_NAMES['asr'])
            result = ensure_model(client, MODEL_NAMES['asr'])
            self.assertEqual(result['state'], 'already_present')
            self.assertEqual(state['pulls'], 0)

    def test_known_small_model_may_be_downloaded(self):
        with fake_ollama() as (client, state):
            model = 'frozenlab/qwen3-asr:0.6b'
            self.assertIn(model, OLLAMA_ASR_DOWNLOADABLE)
            result = ensure_model(client, model, sleep=lambda _: None)
            self.assertEqual(result['model'], model)
            self.assertEqual(state['pulls'], 1)

    def test_unknown_publisher_not_auto_downloaded(self):
        with fake_ollama() as (client, state):
            args = install_all.parse_args(['--profile','models','--ollama-asr-model','unknown/asr:latest'])
            with tempfile.TemporaryDirectory() as td:
                runner = install_all.Installer(args, root=Path(td))
                runner.client, runner.ollama_ok = client, True
                with self.assertRaises(InstallFailure) as e:
                    runner.ollama_asr()
                self.assertEqual(e.exception.code, 'MODEL_SCOPE')
                self.assertEqual(state['pulls'], 0)
                runner.finish()

    def test_ollama_profile_downloads_before_activation(self):
        args = install_all.parse_args(['--profile', 'asr', '--asr-profile', 'ollama17'])
        with tempfile.TemporaryDirectory() as td, fake_ollama() as (client, state):
            runner = install_all.Installer(args, root=Path(td))
            runner.client, runner.ollama_ok, runner.runtime_ok = client, True, True
            with patch.object(runner, 'command') as cmd:
                result = runner.asr()
            self.assertEqual(state['pulls'], 1)
            self.assertEqual(result['selected_profile'], 'ollama17')
            self.assertIn('--model', cmd.call_args.args[0])
            self.assertEqual(cmd.call_args.args[0][-1], MODEL_NAMES['asr'])
            self.assertFalse((Path(td)/'asr_profile.local.json').exists())
            runner.finish()

    def test_failure_does_not_activate_or_overwrite_preferences(self):
        args = install_all.parse_args(['--profile', 'asr', '--asr-profile', 'ollama17'])
        with tempfile.TemporaryDirectory() as td, fake_ollama('dns') as (client, state):
            config = Path(td)/'asr_profile.local.json'
            config.write_text('{"profile":"legacy"}', encoding='utf-8')
            runner = install_all.Installer(args, root=Path(td))
            runner.client, runner.ollama_ok, runner.runtime_ok = client, True, True
            with patch.object(runner, 'command') as cmd, self.assertRaises(InstallFailure) as e:
                runner.asr()
            self.assertEqual(e.exception.code, 'DNS_NON_PUBLIC')
            self.assertEqual(state['pulls'], 1)
            cmd.assert_not_called()
            self.assertEqual(json.loads(config.read_text())['profile'], 'legacy')
            runner.finish()

    def test_custom_installed_model_checked_but_never_pulled(self):
        tag = 'my-local-qwen-asr:latest'
        args = install_all.parse_args(['--profile','models','--ollama-asr-model',tag])
        with tempfile.TemporaryDirectory() as td, fake_ollama() as (client, state):
            state['models'].add(tag)
            runner = install_all.Installer(args, root=Path(td))
            runner.client, runner.ollama_ok = client, True
            result = runner.ollama_asr()
            self.assertEqual(result['state'], 'already_present')
            self.assertEqual(state['pulls'], 0)
            runner.finish()

    def test_existing_profile_and_model_are_not_modified_by_preload(self):
        with tempfile.TemporaryDirectory() as td, fake_ollama() as (client, state):
            config = Path(td)/'asr_profile.local.json'
            config.write_text('{"profile":"ollama17","model":"frozenlab/qwen3-asr:0.6b"}', encoding='utf-8')
            args = install_all.parse_args(['--profile','models'])
            runner = install_all.Installer(args, root=Path(td))
            runner.client, runner.ollama_ok = client, True
            result = runner.ollama_asr()
            self.assertEqual(result['model'], 'frozenlab/qwen3-asr:0.6b')
            self.assertEqual(state['pulls'], 1)
            self.assertEqual(json.loads(config.read_text())['model'], 'frozenlab/qwen3-asr:0.6b')
            runner.finish()

if __name__ == '__main__': unittest.main()
