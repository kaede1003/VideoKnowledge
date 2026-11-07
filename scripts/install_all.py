"""One installer entry for VideoKnowledge (Windows). No changes to app algorithms.

Use INSTALL_ALL.bat. --plan never downloads or installs. --profile diagnose only
checks local service metadata and public download-domain DNS; it does not pull.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time

from install_support import (BLOB_HOST, INSTALLER_VERSION, MODEL_NAMES, OLLAMA_ASR_DOWNLOADABLE, PROBE_HOSTS,
                             InstallFailure, InstallerLock, OllamaClient, dns_probe,
                             ensure_model, redact, validate_asr_tag, write_json_atomic)

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'all': ['runtime', 'review', 'video', 'text', 'vision', 'ollama_asr', 'asr', 'speaker'],
    'core': ['runtime', 'review', 'asr', 'text', 'ollama_asr'],
    'models': ['text', 'vision', 'ollama_asr'],
    'text': ['text'], 'vision': ['vision'], 'asr': ['runtime', 'asr'],
    'speaker': ['runtime', 'speaker'], 'review': ['runtime', 'review'],
    'video': ['runtime', 'video'], 'diagnose': [],
}


def plan(profile: str, asr_model: str, asr_profile: str = 'keep') -> list[dict]:
    labels = {
        'runtime': '本地服务 Python 依赖 / WebSocket',
        'review': '上下文同音词校验组件',
        'video': '视频下载组件及 FFmpeg / Deno 检查',
        'speaker': '说话人分组组件、模型与静音加载检查',
        'asr': (f'ASR 引擎安装与加载检查：{asr_profile}（Ollama模型缺失则自动下载、不安装PyTorch；原生Qwen仍需独立环境）' if asr_profile != 'keep' else f'检查当前ASR配置；旧配置预下载 Whisper {asr_model}'),
        'ollama_asr': 'Ollama 语音模型 Qwen3-ASR（已安装则跳过，缺少才拉取；不切换现有引擎）',
        'text': f'本地文字模型 {MODEL_NAMES["text"]}',
        'vision': f'本地视觉模型 {MODEL_NAMES["vision"]}',
    }
    return [{'id': name, 'description': labels[name]} for name in PROFILES[profile]]


def refresh_path() -> None:
    if os.name != 'nt':
        return
    import winreg
    paths = [os.environ.get('PATH', '')]
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'),
                      (winreg.HKEY_CURRENT_USER, r'Environment')):
        try:
            with winreg.OpenKey(hive, key) as handle:
                paths.append(os.path.expandvars(winreg.QueryValueEx(handle, 'Path')[0]))
        except OSError:
            pass
    paths += [str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet' / 'Links'),
              str(Path.home() / '.deno' / 'bin')]
    os.environ['PATH'] = os.pathsep.join(dict.fromkeys(p for p in paths if p))


def executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if name == 'ollama':
        candidates = [os.environ.get('VKN_OLLAMA_EXE', ''),
                      str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'ollama.exe'),
                      str(Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Ollama' / 'ollama.exe')]
        return next((x for x in candidates if x and Path(x).is_file()), None)
    return None


def port_active(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def supported_deno() -> bool:
    path = executable('deno')
    if not path:
        return False
    try:
        text = subprocess.check_output([path, '--version'], timeout=10, text=True)
        # Require Deno 2 for the video helper. Existing older Deno is not silently upgraded.
        return int(text.split()[1].split('.')[0]) >= 2
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return False


def missing_system_tools(parts: list[str], client: OllamaClient) -> list[tuple[str, str]]:
    missing = []
    if any(x in parts for x in ('text', 'vision', 'ollama_asr')):
        try:
            client.request_json('GET', '/api/version', timeout=3)
        except InstallFailure:
            if not executable('ollama'):
                missing.append(('ollama', 'Ollama.Ollama'))
    if 'video' in parts:
        if not (executable('ffmpeg') and executable('ffprobe')):
            missing.append(('ffmpeg', 'Gyan.FFmpeg'))
        if not supported_deno():
            missing.append(('deno', 'DenoLand.Deno'))
    return missing


class Installer:
    def __init__(self, args, *, root: Path = ROOT):
        self.args, self.root = args, root
        self.parts = PROFILES[args.profile]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        self.out = root / 'diagnostics' / 'install'
        self.out.mkdir(parents=True, exist_ok=True)
        self.json_path = self.out / ('install-' + stamp + '.json')
        self.log_path = self.out / ('install-' + stamp + '.log')
        self.log = self.log_path.open('w', encoding='utf-8', buffering=1)
        self.report = {'installer_version': INSTALLER_VERSION, 'app_version': '0.11.3',
                       'started_utc': stamp, 'profile': args.profile, 'steps': [],
                       'models': {}, 'all_selected_ready': False,
                       'scope': 'Installation checks; not real Edge/ASR/Ollama quality acceptance'}
        self.client = OllamaClient(args.ollama_url)
        self.runtime_ok = False
        self.ollama_ok = None
        self.blocked_download = None
        self.last_progress = 0.0
        self.last_phase = ''
        self.owned_ollama = None
        self.save()

    def say(self, message: str):
        safe = redact(message)
        print(safe, flush=True)
        if self.log.tell() > 10 * 1024 * 1024:
            self.log.close()
            previous = self.log_path.with_suffix('.previous.log')
            os.replace(self.log_path, previous)
            self.log = self.log_path.open('w', encoding='utf-8', buffering=1)
        self.log.write(safe + '\n')

    def save(self):
        write_json_atomic(self.json_path, self.report)

    def command(self, args: list[str], *, timeout=1800, attempts=1, env=None):
        """Show bounded sanitized child output; never use shell=True or global kills."""
        for attempt in range(attempts):
            self.say('[RUN] ' + ' '.join(str(x) for x in args))
            merged = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
            if env:
                merged.update(env)
            # Let only this wrapper handle Ctrl+C, then stop only its own child tree.
            options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
                       else {'start_new_session': True})
            proc = subprocess.Popen(args, cwd=self.root, env=merged, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, **options)
            messages = queue.Queue(maxsize=512)
            finished = threading.Event()
            def reader():
                try:
                    while block := proc.stdout.read1(4096):
                        # Limit memory if an unusually chatty package installer is used.
                        while not finished.is_set():
                            try:
                                messages.put(block, timeout=.2); break
                            except queue.Full:
                                pass
                except (OSError, ValueError):
                    pass
                finally:
                    while not finished.is_set():
                        try:
                            messages.put(None, timeout=.2); break
                        except queue.Full:
                            pass
            threading.Thread(target=reader, daemon=True).start()
            start, tail, buffer = time.monotonic(), '', ''
            try:
                while True:
                    if time.monotonic() - start > timeout:
                        raise InstallFailure('Installer child deadline exceeded', code='CHILD_TIMEOUT', retryable=True)
                    try:
                        block = messages.get(timeout=.25)
                    except queue.Empty:
                        continue
                    if block is None:
                        break
                    buffer += block.decode('utf-8', 'replace').replace('\r', '\n')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            self.say(line[:4000]); tail = (tail + '\n' + line)[-12000:]
                    if len(buffer) > 16000:
                        self.say(buffer[:4000]); tail = (tail + buffer)[-12000:]; buffer = ''
                if buffer:
                    self.say(buffer); tail = (tail + buffer)[-12000:]
                remaining = max(1, timeout - (time.monotonic() - start))
                rc = proc.wait(timeout=remaining)
                if rc == 0:
                    return
                fail = InstallFailure(tail or f'Child exited {rc}', code='CHILD_FAILED')
                if not fail.retryable or attempt + 1 >= attempts:
                    raise fail
                self.say('[RETRY] Package helper failed transiently; retrying without clearing caches.')
                time.sleep(min(15, 5 * (attempt + 1)))
            finally:
                finished.set()
                if proc.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                    else:
                        import signal
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill(); proc.wait(timeout=5)
                if proc.stdout:
                    proc.stdout.close()

    def step(self, name: str, callback) -> bool:
        entry = {'name': name, 'status': 'running'}
        self.report['steps'].append(entry); self.save()
        self.say('\n[STEP] ' + name)
        start = time.monotonic()
        try:
            detail = callback()
            entry.update(status='ready', detail=detail)
            self.say('[OK] ' + name)
            return True
        except KeyboardInterrupt:
            entry.update(status='cancelled', code='USER_CANCELLED')
            self.say('[STOP] 用户取消；已安装的组件和下载缓存未删除。')
            raise
        except Exception as exc:
            entry.update(status='failed', code=getattr(exc, 'code', type(exc).__name__), error=redact(exc)[:2000])
            self.say('[FAIL] ' + redact(exc))
            if isinstance(exc, InstallFailure):
                self.say(exc.hint)
            return False
        finally:
            entry['seconds'] = round(time.monotonic() - start, 2)
            self.save()

    def network_report(self):
        results = [dns_probe(host) for host in PROBE_HOSTS]
        self.report['dns'] = results
        self.report['proxy_environment'] = {key: bool(os.environ.get(key)) for key in ('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'NO_PROXY')}
        for row in results:
            self.say('[DNS] ' + row['host'] + ': ' + row['status'] + ' ' + ', '.join(x['ip'] for x in row['addresses']))
        if any(row['status'] == 'non-public' for row in results):
            self.say('[WARN] 发现非公网解析，可能是 Fake-IP。实际拉取若被拒绝，不会反复重试或关闭安全检查。')
            self.say('[HELP] 参阅 docs/INSTALL_ALL_CN.md 的“Fake-IP”段，修复域名解析后重新运行同一个安装入口。')
        if os.environ.get('HTTP_PROXY'):
            self.say('[WARN] 检测到 HTTP_PROXY；本工具直连回环接口，但已运行 Ollama 的出网环境需另外核对。')
        self.save()
        return results

    def install_system_tools(self):
        refresh_path()
        parts = list(self.parts)
        if 'asr' in parts and self.effective_asr_selection()[0] == 'ollama17':
            parts.append('ollama_asr')
        missing = missing_system_tools(parts, self.client)
        if not missing:
            return {'missing': []}
        packages = [p for _, p in missing]
        self.say('[MISSING] ' + ', '.join(packages))
        if self.args.skip_system_tools:
            raise InstallFailure('缺少系统组件；按选项未安装。可以稍后重跑同一个入口。', code='SYSTEM_TOOLS_MISSING', retryable=False)
        if not executable('winget'):
            raise InstallFailure('WinGet 不可用。请使用官方 Python/Ollama/FFmpeg/Deno 安装方式，再重跑。', code='WINGET_MISSING', retryable=False)
        consent = self.args.yes
        if not consent:
            self.say('允许通过 WinGet 安装以上缺少的软件？这会接受对应安装协议，可能出现系统确认窗口。')
            try:
                consent = input('输入 Y 继续，其他键跳过: ').strip().lower() == 'y'
            except EOFError:
                consent = False
        if not consent:
            raise InstallFailure('系统组件安装未获确认；继续检查其余部分，结尾不会报告全成功。', code='SYSTEM_INSTALL_DECLINED', retryable=False)
        failures = []
        for command, package in missing:
            try:
                self.command([executable('winget'), 'install', '--id', package, '--exact', '--source', 'winget',
                              '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity'], timeout=3600)
                refresh_path()
                available = (executable(command) and (command != 'deno' or supported_deno()))
                if command == 'ffmpeg':
                    available = available and executable('ffprobe')
                if not available:
                    raise InstallFailure('安装后仍无法找到可用命令；请关闭终端后重开，再运行一次。', code='PATH_REFRESH', retryable=False)
            except Exception as exc:
                failures.append(package + ': ' + redact(exc))
        if failures:
            raise InstallFailure('; '.join(failures), code='SYSTEM_PARTIAL', retryable=False)
        return {'installed': packages}

    def pip(self, *args, binary=False):
        command = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--retries', '3', '--timeout', '90']
        if binary:
            command.append('--only-binary=:all:')
        self.command(command + list(args), timeout=3600)

    def runtime(self):
        self.pip('-r', 'server/requirements.txt')
        self.command([sys.executable, '-c', 'import fastapi,uvicorn,faster_whisper,numpy,httpx,PIL,websockets'], timeout=120)
        (self.root / '.venv' / '.vkn_deps_v050.ok').write_text('v050\n', encoding='ascii')
        self.runtime_ok = True
        return {'imports_verified': True, 'service_started': False}

    def review(self):
        self.pip('pypinyin==0.55.0')
        self.command([sys.executable, '-c', 'from pypinyin import lazy_pinyin; assert lazy_pinyin("hello")'], timeout=30)
        return {'package_imported': True, 'reasoning_model_tested': False}

    def video(self):
        self.pip('yt-dlp[default]>=2025.11.12')
        self.command([sys.executable, '-m', 'yt_dlp', '--version'], timeout=30)
        if not (executable('ffmpeg') and executable('ffprobe') and supported_deno()):
            raise InstallFailure('yt-dlp 已安装，但完整视频合并/解析工具未齐备。需要 FFmpeg、ffprobe 和 Deno 2。',
                                 code='VIDEO_TOOLS_MISSING', retryable=False)
        self.command([executable('ffmpeg'), '-version'], timeout=30)
        return {'packages_imported': True, 'ffmpeg': True, 'deno2': True, 'site_download_tested': False}

    def speaker(self):
        if not self.runtime_ok:
            raise InstallFailure('本地运行依赖未完成；没有在残缺环境中安装说话人模型。', code='DEPENDENCY', retryable=False)
        self.pip('-r', 'server/requirements-speaker.txt', binary=True)
        self.command([sys.executable, 'scripts/install_speaker_models.py'], timeout=3600, attempts=3)
        return {'model_load_and_silence_check': True, 'speaker_accuracy_tested': False}

    def effective_asr_selection(self) -> tuple[str, str | None]:
        selected = self.args.asr_profile
        saved_model = None
        if selected == 'keep' and (self.root / 'asr_profile.local.json').is_file():
            saved = json.loads((self.root / 'asr_profile.local.json').read_text(encoding='utf-8'))
            selected = saved.get('profile', 'legacy')
            if selected == 'ollama17':
                saved_model = saved.get('model')
        return selected, saved_model

    def ollama_asr_tag(self) -> str:
        # CLI wins; otherwise preserve a configured Ollama tag, then use the
        # documented default. Never rewrite the user's preferences here.
        selected, saved_model = self.effective_asr_selection()
        name = self.args.ollama_asr_model or (saved_model if selected == 'ollama17' else None) or MODEL_NAMES['asr']
        return validate_asr_tag(name)

    def ollama_asr(self):
        return self.model('asr')

    def asr(self):
        if not self.runtime_ok:
            raise InstallFailure('本地运行依赖未完成，ASR 安装暂缓。', code='DEPENDENCY', retryable=False)
        selected, _ = self.effective_asr_selection()
        if selected == 'ollama17':
            # An explicit ASR selection is only activated after both a real
            # model download/metadata check and the existing audio smoke test.
            tag = self.ollama_asr_tag()
            result = self.report['models'].get('asr', {})
            if result.get('model') != tag:
                self.ollama_asr()
        if selected not in ('keep', 'legacy') or self.args.asr_profile == 'legacy':
            cmd = [sys.executable, 'scripts/setup_asr_profile.py', '--profile', selected]
            if selected == 'ollama17':
                cmd += ['--model', self.ollama_asr_tag()]
            self.command(cmd, timeout=10800)
            return {'selected_profile': selected, 'activation_after_load_check': True, 'accuracy_tested': False}
        # Legacy mode reuses the pre-existing model/settings.
        self.command([sys.executable, 'scripts/prefetch_asr.py', '--model', self.args.asr_model], timeout=7200, attempts=3)
        return {'model': self.args.asr_model, 'model_load_verified': True, 'speech_accuracy_tested': False}

    def ensure_ollama(self):
        try:
            data = self.client.request_json('GET', '/api/version', timeout=5)
            self.ollama_ok = True
            return data
        except InstallFailure:
            pass
        # Never kill a listener or change an existing application's server environment.
        if port_active(self.client.port):
            raise InstallFailure('Ollama 端口已有进程，但接口未通过。请检查端口对应服务。', code='OLLAMA_PORT_BUSY', retryable=False)
        binary = executable('ollama')
        if not binary:
            raise InstallFailure('Ollama 未安装或命令不可用。', code='OLLAMA_MISSING', retryable=False)
        self.say('[INFO] 本机无 Ollama 服务，启动已安装的 Ollama serve（仅回环监听）。')
        env = dict(os.environ)
        host = '[' + self.client.host + ']' if ':' in self.client.host else self.client.host
        env['OLLAMA_HOST'] = f'{host}:{self.client.port}'
        # Do NOT clear the user's HTTPS_PROXY/NO_PROXY or change OLLAMA_MODELS.
        options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                   if os.name == 'nt' else {'start_new_session': True})
        self.owned_ollama = subprocess.Popen([binary, 'serve'], env=env, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        self.report['started_ollama_pid'] = self.owned_ollama.pid
        self.report['ollama_daemon_left_running'] = True
        end = time.monotonic() + 45
        while time.monotonic() < end:
            try:
                data = self.client.request_json('GET', '/api/version', timeout=3)
                self.ollama_ok = True
                return data
            except InstallFailure:
                if self.owned_ollama.poll() is not None:
                    break
                time.sleep(1)
        raise InstallFailure('Ollama 服务未就绪。请从开始菜单启动 Ollama 后重跑；没有强杀其他进程。', code='OLLAMA_START', retryable=False)

    def progress(self, row):
        now, status = time.monotonic(), row['status']
        if now - self.last_progress < 2 and status == self.last_phase:
            return
        self.last_progress, self.last_phase = now, status
        if row['total']:
            percent = min(100, row['completed'] * 100 / row['total'])
            self.say(f'[PROGRESS] {status} {percent:.1f}% ({row["completed"]/1048576:.1f}/{row["total"]/1048576:.1f} MiB)')
        else:
            self.say('[PROGRESS] ' + status)

    def model(self, role):
        name = self.ollama_asr_tag() if role == 'asr' else MODEL_NAMES[role]
        if self.ollama_ok is None:
            self.report['ollama'] = self.ensure_ollama()
        if not self.ollama_ok:
            raise InstallFailure('本机 Ollama 接口尚未就绪。', code='OLLAMA_UNAVAILABLE', retryable=False)
        if role == 'asr' and name not in OLLAMA_ASR_DOWNLOADABLE and not self.client.model_present(name):
            raise InstallFailure('该自定义 ASR 模型未安装。仅自动下载 frozenlab/qwen3-asr 的 1.7b/0.6b 已知标签；其他标签请自行确认来源并安装。',
                                 code='MODEL_SCOPE', retryable=False)
        if self.blocked_download and not self.client.model_present(name):
            raise InstallFailure('前一模型已确认下载网络/安全策略拒绝，暂缓相同来源的新下载。修复网络后重跑。',
                                 code='DOWNLOAD_NETWORK_BLOCKED', retryable=False)
        try:
            result = ensure_model(self.client, name, attempts=self.args.retries,
                                  idle_timeout=self.args.idle_timeout, stall_timeout=self.args.stall_timeout,
                                  total_timeout=self.args.model_timeout, progress=self.progress, notify=self.say)
            self.report['models'][role] = result
            return result
        except InstallFailure as exc:
            if exc.code in {'DNS_NON_PUBLIC', 'TLS_CERTIFICATE', 'ACCESS_DENIED'}:
                self.blocked_download = exc.code
            raise

    def finish(self, cancelled=False):
        failed = [x for x in self.report['steps'] if x['status'] != 'ready']
        self.report['cancelled'] = cancelled
        self.report['all_selected_ready'] = not failed and not cancelled
        self.report['completed_utc'] = datetime.now(timezone.utc).isoformat()
        self.save()
        self.say('\n========== 安装结果 ==========')
        for row in self.report['steps']:
            self.say(('  OK  ' if row['status'] == 'ready' else '  FAIL  ') + row['name'] +
                     (' [' + row.get('code', '') + ']' if row['status'] != 'ready' else ''))
        self.say('[REPORT] ' + str(self.json_path))
        if self.args.profile == 'diagnose':
            self.say('[NOTE] 诊断没有下载模型；DNS/接口正常也不等于推理或 Edge 采集已验收。')
        elif self.report['all_selected_ready']:
            self.say('[OK] 所选安装检查通过。运行 START_LOCAL_ASR.bat，再在 Edge 加载/保留原 extension 目录。')
            self.say('[NOTE] 浏览器扩展加载和采集授权需你在 Edge 确认，安装器不会代替授权。')
        else:
            self.say('[PARTIAL] 部分步骤未完成。已装组件保留；修复报告中的问题后只需重新运行 INSTALL_ALL.bat。')
        self.say('[NOTE] 本地模型元数据检查不是实际推理/识别质量测试；安装器不解决已有长文100秒超时。')
        self.log.close()
        return 130 if cancelled else 1 if failed else 0

    def run(self):
        self.say('VideoKnowledge 统一安装器 ' + INSTALLER_VERSION + ' | 服务0.11.3 / Ollama ASR 自动补装')
        self.say('不清空笔记/模型；不关闭 TLS/重定向安全检查；不自动修改系统代理、DNS 或 hosts。')
        if self.args.profile == 'asr' and getattr(self.args,'asr_profile','keep') == 'legacy':
            if port_active(8765):
                self.report['steps'].append({'name':'停止旧服务后切换','status':'failed','code':'ASR_RUNNING'})
                return self.finish()
            self.step('恢复旧ASR设置（不下载、不删除模型）', lambda: self.command(
                [sys.executable,'scripts/setup_asr_profile.py','--profile','legacy'],timeout=30))
            return self.finish()
        if self.args.profile == 'asr' and getattr(self.args,'asr_profile','keep') == 'ollama17':
            self.say('[INFO] Selected Ollama ASR; missing model is downloaded through /api/pull; no PyTorch/Transformers installation.')
        else:
            self.network_report()
        if self.args.profile == 'diagnose':
            self.step('Ollama 本机接口', lambda: self.client.request_json('GET', '/api/version', timeout=5))
            self.step('本机模型列表', lambda: sorted(self.client.models()))
            if any(row['status'] != 'public' for row in self.report['dns']):
                code = 'DNS_NON_PUBLIC' if any(row['status'] == 'non-public' for row in self.report['dns']) else 'DNS_UNVERIFIED'
                self.report['steps'].append({'name': '下载域名解析', 'status': 'failed', 'code': code,
                                             'note': '这是安装进程的 DNS 结果；实际守护进程网络还应结合拉取错误。'})
            return self.finish()
        if any(x in self.parts for x in ('runtime', 'review', 'video', 'speaker', 'asr')) and port_active(8765):
            self.report['steps'].append({'name': '停止旧本地服务后再安装', 'status': 'failed', 'code': 'ASR_RUNNING'})
            self.say('[BLOCKED] 8765端口正在使用。请停止本项目服务后再安装；不会自动终止它。')
            return self.finish()
        self.step('检查 / 补齐系统工具', self.install_system_tools)
        handlers = {'runtime': self.runtime, 'review': self.review, 'video': self.video,
                    'speaker': self.speaker, 'asr': self.asr, 'ollama_asr': self.ollama_asr,
                    'text': lambda: self.model('text'), 'vision': lambda: self.model('vision')}
        try:
            # Core deps first. Models are sequential, never several multi-GB pulls at once.
            for part in self.parts:
                self.step(next(x['description'] for x in plan(self.args.profile, self.args.asr_model, getattr(self.args,'asr_profile','keep')) if x['id'] == part), handlers[part])
        except KeyboardInterrupt:
            return self.finish(cancelled=True)
        return self.finish()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', choices=PROFILES, default='all')
    p.add_argument('--plan', action='store_true')
    p.add_argument('--yes', action='store_true', help='Explicit consent to missing WinGet packages and their agreements')
    p.add_argument('--skip-system-tools', action='store_true')
    p.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    p.add_argument('--asr-profile',choices=['keep','legacy','ollama17','qwen17','qwen06','whisper-large','whisper-turbo'],default='keep')
    p.add_argument('--ollama-asr-model', default=None, help='Exact tag shown by Ollama, default frozenlab/qwen3-asr:1.7b')
    p.add_argument('--asr-model', default=os.environ.get('VKN_ASR_MODEL', 'small'))
    p.add_argument('--retries', type=int, choices=range(1, 7), default=3)
    p.add_argument('--idle-timeout', type=float, default=180, help='Seconds without stream bytes')
    p.add_argument('--stall-timeout', type=float, default=600, help='Seconds without status/byte-count advancement')
    p.add_argument('--model-timeout', type=float, default=14400, help='Absolute per-pull safety limit, not an estimate')
    a = p.parse_args(argv)
    if min(a.idle_timeout, a.stall_timeout, a.model_timeout) <= 0:
        p.error('Timeouts must be positive')
    return a


def main(argv=None):
    args = parse_args(argv)
    if args.plan:
        print(json.dumps({'installer': INSTALLER_VERSION, 'profile': args.profile, 'steps': plan(args.profile, args.asr_model,args.asr_profile),
                          'automatic_system_changes': 'WinGet only with consent; no proxy/DNS/security changes'}, ensure_ascii=False, indent=2))
        return 0
    if os.name != 'nt' and args.profile != 'diagnose':
        print('[ERROR] 安装仅针对 Windows；当前平台可以使用 --plan 或 --profile diagnose。')
        return 2
    if args.profile != 'diagnose' and Path(sys.executable).resolve() != (ROOT / '.venv' / 'Scripts' / 'python.exe').resolve():
        print('[ERROR] 请运行 INSTALL_ALL.bat，确保包安装到本项目 .venv，不修改全局 Python。')
        return 2
    try:
        with InstallerLock(ROOT / 'diagnostics' / 'install' / '.install.lock'):
            runner = Installer(args)
            try:
                return runner.run()
            except KeyboardInterrupt:
                return runner.finish(cancelled=True)
            except Exception as exc:
                runner.report['steps'].append({'name': '安装器', 'status': 'failed', 'error': redact(exc), 'code': 'INSTALLER_ERROR'})
                runner.say('[ERROR] ' + redact(exc))
                return runner.finish()
    except InstallFailure as exc:
        print(redact(exc)); return 2


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
