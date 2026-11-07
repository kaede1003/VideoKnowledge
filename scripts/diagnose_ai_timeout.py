#!/usr/bin/env python3
"""Read-only local Ollama timing diagnostic; no third-party dependencies.

Only canned text is sent to a loopback Ollama server. Model generations consume
resources but no settings, models, notes, credentials, or processes are changed.
Reports intentionally omit response text and request text.
"""
from __future__ import annotations
import argparse
import datetime as dt
import http.client
import json
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

VERSION = "1.0"
MAX_BODY = 2 * 1024 * 1024


def local_target(base_url: str) -> tuple[str, int]:
    u = urlsplit(base_url)
    if (u.scheme != "http" or u.hostname not in {"127.0.0.1", "localhost"}
            or u.username or u.password or u.query or u.fragment or u.path not in {"", "/"}):
        raise ValueError("Only an HTTP loopback origin is permitted, e.g. http://127.0.0.1:11434")
    # Connect to the literal address: no DNS resolution or proxy settings.
    return "127.0.0.1", u.port or 11434


def validate_model(model: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,120}", model) or "cloud" in model.lower():
        raise ValueError("Choose an installed local model, not a cloud model.")
    return model


def request(base_url: str, path: str, payload: dict | None = None,
            deadline: float = 180.0, streaming: bool = False) -> dict[str, Any]:
    host, port = local_target(base_url)
    if path not in {"/api/version", "/api/tags", "/api/ps", "/api/chat"}:
        raise ValueError("Endpoint not permitted by this diagnostic")
    start = time.monotonic()
    row: dict[str, Any] = {"endpoint": path, "ok": False, "deadline_s": deadline}
    conn = http.client.HTTPConnection(host, port, timeout=min(10.0, deadline))
    state: dict[str, Any] = {"socket": None}
    expired = threading.Event()
    def abort() -> None:
        expired.set()
        s = state["socket"]
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        conn.close()
    timer = threading.Timer(deadline, abort)
    timer.daemon = True
    timer.start()
    total_bytes = 0
    buffer = b""
    final: dict[str, Any] | None = None
    try:
        conn.connect()
        if expired.is_set():
            raise TimeoutError()
        state["socket"] = conn.sock
        conn.sock.settimeout(max(0.05, deadline - (time.monotonic() - start)))
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        conn.request("GET" if payload is None else "POST", path, body=body,
                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        resp = conn.getresponse()
        row.update(http_status=resp.status, headers_s=round(time.monotonic() - start, 4))
        if resp.status != 200:
            # Never log raw error responses; they can contain private request data.
            row["error"] = "HTTP_" + str(resp.status)
            return row
        output_chars = 0
        thought_chars = 0
        while True:
            data = resp.read1(65536)
            if expired.is_set():
                raise TimeoutError()
            if not data:
                break
            total_bytes += len(data)
            if total_bytes > MAX_BODY:
                row["error"] = "RESPONSE_TOO_LARGE"
                return row
            row.setdefault("first_byte_s", round(time.monotonic() - start, 4))
            buffer += data
            if not streaming:
                continue
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("Invalid response frame")
                if "error" in item:
                    row["error"] = "OLLAMA_STREAM_ERROR"
                    return row
                message = item.get("message", {})
                if isinstance(message, dict):
                    content = message.get("content", "")
                    thought = message.get("thinking", "")
                    if isinstance(content, str) and content:
                        row.setdefault("first_content_s", round(time.monotonic() - start, 4))
                        output_chars += len(content)
                    if isinstance(thought, str):
                        thought_chars += len(thought)
                if item.get("done") is True:
                    final = item
        if streaming:
            if buffer.strip():
                item = json.loads(buffer)
                if "error" in item:
                    row["error"] = "OLLAMA_STREAM_ERROR"
                    return row
                message = item.get("message", {})
                content = message.get("content", "") if isinstance(message, dict) else ""
                if isinstance(content, str) and content:
                    row.setdefault("first_content_s", round(time.monotonic() - start, 4))
                    output_chars += len(content)
                if item.get("done") is True:
                    final = item
            row["output_chars"] = output_chars
            row["thinking_chars"] = thought_chars
            if final is None:
                row["error"] = "STREAM_ENDED_WITHOUT_DONE"
                return row
            row["finish_reason"] = str(final.get("done_reason", "unknown"))[:40]
            for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
                value = final.get(key)
                if isinstance(value, (int, float)) and value >= 0:
                    row[key.replace("_duration", "_s")] = round(value / 1e9, 4)
            for key in ("prompt_eval_count", "eval_count"):
                if isinstance(final.get(key), int):
                    row[key] = final[key]
            if row.get("eval_s", 0) > 0:
                row["output_tokens_per_s"] = round(row.get("eval_count", 0) / row["eval_s"], 2)
            row["ok"] = output_chars > 0
            if not row["ok"]:
                row["error"] = "NO_VISIBLE_CONTENT"
        else:
            row["data"] = json.loads(buffer)
            row["ok"] = True
    except (KeyboardInterrupt, SystemExit):
        abort()
        raise
    except Exception as exc:
        row["error"] = "LOCAL_DEADLINE" if expired.is_set() or isinstance(exc, (TimeoutError, socket.timeout)) else type(exc).__name__
    finally:
        timer.cancel()
        conn.close()
        row["wall_s"] = round(time.monotonic() - start, 4)
        row["body_bytes"] = total_bytes
    return row


def running_models(base_url: str) -> dict[str, Any]:
    r = request(base_url, "/api/ps", deadline=10)
    data = r.pop("data", {})
    r["models"] = [{k: x.get(k) for k in ("name", "size", "size_vram", "context_length", "expires_at")}
                   for x in data.get("models", []) if isinstance(x, dict)] if isinstance(data, dict) else []
    return r


def gpu_snapshot() -> dict[str, Any]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"available": False}
    try:
        p = subprocess.run([exe, "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True,
                           timeout=8, encoding="utf-8", errors="replace")
        return {"available": p.returncode == 0, "snapshot": p.stdout.strip()[:1500] if p.returncode == 0 else ""}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False}


def canned_medium() -> str:
    lines = []
    for i in range(70):
        lines.append(f"[{i // 6:02d}:{(i % 6) * 10:02d}] 测试记录{i+1}：这是一段软件测试资料。"
                     "记录应保留原文、时间顺序、数据来源和不确定之处。程序在本地处理声音与文字，"
                     "整理时不能编造缺失的信息。例子只用于性能检测，不是真实视频内容。")
    return "请将以下测试记录整理为中文知识笔记，列出方法、限制和待验证事项，控制在500字以内。\n" + "\n".join(lines)


def hints(report: dict[str, Any]) -> list[str]:
    out = []
    for r in report.get("tests", []):
        name = r["name"]
        if not r.get("ok"):
            out.append(f"{name}: {r.get('error', 'failed')}。本机诊断也未完成；不能仅归因于插件。")
            continue
        if r.get("wall_s", 0) > 100:
            out.append(f"{name}: 本次本机测试完成耗时超过100秒；旧插件的100秒总期限可能会中断同等或更重任务。")
        if r.get("load_s", 0) > 5:
            out.append(f"{name}: 服务端报告模型加载耗时 {r['load_s']} 秒；首轮慢可能包括模型加载。")
        if r.get("prompt_eval_s", 0) > 10:
            out.append(f"{name}: 输入处理耗时 {r['prompt_eval_s']} 秒，长输入处理是可观测的开销。")
        if r.get("eval_s", 0) > 10:
            out.append(f"{name}: 输出生成耗时 {r['eval_s']} 秒，输出长度或生成速度影响总耗时。")
    if not out:
        out.append("短/中等测试未显示明显超时。不能据此证明完整笔记一定在100秒内完成；需结合插件请求长度和当时负载。")
    out += ["first_content_s 包含网络、本机排队、模型加载及输入处理，不能直接当排队秒数。",
            "未保存提示正文或生成正文。未读取/更改笔记、API Key、环境变量、模型文件或服务日志。",
            "本工具测试 /api/chat 流式接口；插件0.7.1为 /v1/chat/completions 非流式，测试不是失败请求的精确重放。",
            "中等测试使用合成文字且最多生成1024 token；它不会测出原插件无输出预算时的所有超时情形。",
            "GPU显存快照不等于Ollama实测速度；需结合运行模型列表，不能仅凭显存占用判断GPU是否正确加速。"]
    return out


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    local_target(args.base_url)
    validate_model(args.model)
    report: dict[str, Any] = {"tool_version": VERSION, "time": dt.datetime.now().astimezone().isoformat(),
                             "base_url": args.base_url, "model": args.model, "tests": [],
                             "sample": "canned_non_user_text"}
    code = 0
    try:
        report["ollama_version"] = request(args.base_url, "/api/version", deadline=10)
        tags = request(args.base_url, "/api/tags", deadline=10)
        tagdata = tags.pop("data", {})
        names = [str(m.get("name", m.get("model", ""))) for m in tagdata.get("models", []) if isinstance(m, dict)] if isinstance(tagdata, dict) else []
        tags["installed_count"] = len(names)
        tags["requested_installed"] = args.model in names or (":" not in args.model and args.model + ":latest" in names)
        report["model_check"] = tags
        report["running_before"] = running_models(args.base_url)
        report["gpu_before"] = gpu_snapshot()
        if not tags.get("ok") or not tags["requested_installed"]:
            report["error"] = "OLLAMA_UNAVAILABLE_OR_REQUESTED_MODEL_NOT_INSTALLED"
            return report, 2
        jobs = [("short_initial", "只回复：连接正常。", 32),
                ("short_warm", "只回复：连接正常。", 32)]
        if args.medium:
            jobs.append(("medium_canned", canned_medium(), 1024))
        for name, user, budget in jobs:
            print(f"[RUN] {name}; model={args.model}; input_chars={len(user)}; output_cap={budget}", flush=True)
            payload = {"model": args.model, "stream": True,
                       "messages": [{"role": "system", "content": "你是本地软件性能测试助手，请按用户要求作简短回复。"},
                                    {"role": "user", "content": user}],
                       "options": {"temperature": 0, "num_predict": budget}}
            row = request(args.base_url, "/api/chat", payload, deadline=args.timeout, streaming=True)
            row.update(name=name, input_chars=sum(len(m["content"]) for m in payload["messages"]), output_cap=budget)
            report["tests"].append(row)
            print(f"[RESULT] ok={row['ok']} wall={row.get('wall_s')}s first_content={row.get('first_content_s')}s "
                  f"load={row.get('load_s')}s input={row.get('prompt_eval_s')}s output={row.get('eval_s')}s "
                  f"tokens/s={row.get('output_tokens_per_s')}", flush=True)
            if not row["ok"]:
                code = 2
                # Do not stack another request behind one that may still be computing.
                break
            report["running_after_" + name] = running_models(args.base_url)
    except KeyboardInterrupt:
        report["interrupted"] = True
        code = 130
    finally:
        report["assessment"] = hints(report)
    return report, code


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="qwen2.5:3b")
    p.add_argument("--medium", action="store_true", help="Also run a bounded ~6000-character synthetic input test")
    p.add_argument("--timeout", type=float, default=180, help="Absolute deadline per inference request (5..600 seconds)")
    p.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent.parent / "diagnostics")
    args = p.parse_args()
    if not 5 <= args.timeout <= 600:
        p.error("--timeout must be between 5 and 600")
    try:
        local_target(args.base_url)
        validate_model(args.model)
    except ValueError as e:
        p.error(str(e))
    print("Video Knowledge - local AI timeout diagnostic", flush=True)
    print("No notes/keys are read. No model download or configuration change. Ctrl+C cancels.", flush=True)
    report, code = run(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = "ai-timeout-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = args.output_dir / (stem + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    txt = ["本地模型超时诊断（只读配置；使用合成测试文字）", f"模型：{args.model}"]
    for t in report["tests"]:
        txt.append(f"{t['name']}: ok={t['ok']}; 总等待={t.get('wall_s')}s; 首段正文={t.get('first_content_s')}s; "
                   f"加载={t.get('load_s')}s; 输入处理={t.get('prompt_eval_s')}s; 输出生成={t.get('eval_s')}s; "
                   f"输出速度={t.get('output_tokens_per_s')}token/s; 错误={t.get('error','无')}")
    txt += ["", *report["assessment"]]
    if report.get("error"):
        txt += ["", "未运行推理：服务不可用或指定模型未安装。本工具不自动安装模型。"]
    path.with_suffix(".txt").write_text("\n".join(txt), encoding="utf-8-sig")
    print("[SAVED] " + str(path), flush=True)
    print("[SAVED] " + str(path.with_suffix('.txt')), flush=True)
    return code

if __name__ == "__main__":
    raise SystemExit(main())
