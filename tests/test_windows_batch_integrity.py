from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class WindowsBatchIntegrityTests(unittest.TestCase):
    def test_all_batch_scripts_ascii_crlf(self):
        scripts = sorted(ROOT.glob('*.bat'))
        self.assertGreaterEqual(len(scripts), 6)
        for script in scripts:
            data = script.read_bytes()
            self.assertTrue(data.isascii(), f'Non-ASCII in {script.name}')
            self.assertFalse(data.startswith(b'\xef\xbb\xbf'), script.name)
            self.assertNotIn(b'\n', data.replace(b'\r\n', b''), script.name)

    def test_legacy_model_installers_delegate_to_safe_unified_entry(self):
        for name, profile in [('INSTALL_LORA_MODEL.bat','vision'), ('INSTALL_TEXT_MODEL.bat','text')]:
            s = (ROOT / name).read_text(encoding='ascii')
            self.assertIn('INSTALL_ALL.bat" -Profile ' + profile, s)
            self.assertIn('exit /b %errorlevel%', s)
            self.assertNotIn(' pull ', s)
        entry = (ROOT / 'INSTALL_ALL.bat').read_text(encoding='ascii')
        self.assertIn('scripts\\install_all.ps1', entry)
        self.assertIn('INSTALL_EXIT=%errorlevel%', entry)

    def test_stop_script_root_argument_has_no_trailing_backslash_quoted(self):
        stop=(ROOT/'STOP_LOCAL_ASR.bat').read_text(encoding='ascii')
        self.assertIn('-ProjectRoot "%~dp0."',stop)
        self.assertNotIn('-ProjectRoot "%~dp0"',stop)

    def test_websocket_transport_required(self):
        req = (ROOT / 'server/requirements.txt').read_text(encoding='utf-8')
        self.assertIn('websockets>=13,<17', req)
        self.assertTrue((ROOT / 'STOP_LOCAL_ASR.bat').exists())
        self.assertTrue((ROOT / 'scripts/check_ws.py').exists())
        self.assertTrue((ROOT / 'scripts/stop_local_asr.ps1').exists())

    def test_asr_upgrade_installs_new_dependencies(self):
        s = (ROOT / 'START_LOCAL_ASR.bat').read_text(encoding='ascii')
        for expected in ['.vkn_deps_v050.ok', 'pip install -r', 'import fastapi, uvicorn, faster_whisper, numpy, httpx, PIL, websockets', '127.0.0.1', 'if errorlevel 1 goto install_error']:
            self.assertIn(expected, s)

if __name__ == '__main__':
    unittest.main()
