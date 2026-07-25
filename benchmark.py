#!/usr/bin/env python3
"""
benchmark.py — Luna Hardware Benchmark

Exercises the Luna kernel (API + tools + memory + planner) and measures
CPU/RAM using native Linux commands (ps, free).  No complex monitoring
infrastructure — just reliable shell tools.

Usage:
    uv run python benchmark.py
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
import requests

# ── Logging ──────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("benchmark")

# ── Config ───────────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent

# ── Helpers ──────────────────────────────────────────────────────────────


def find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def collect_system_info() -> dict[str, Any]:
    cpu = "unknown"
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except OSError:
        cpu = platform.processor() or "unknown"
    ram = psutil.virtual_memory()
    return {
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "cpu": cpu,
        "cores": psutil.cpu_count(logical=True) or 0,
        "ram_gb": round(ram.total / (1024**3), 1),
    }


def disk_usage_mb() -> float:
    total = 0
    for root, _dirs, files in os.walk(PROJECT_DIR):
        parts = Path(root).relative_to(PROJECT_DIR).parts
        if any(p in (".venv", "__pycache__", ".git") for p in parts):
            continue
        for name in files:
            with contextlib.suppress(OSError):
                total += (Path(root) / name).lstat().st_size
    return total / (1024 * 1024)


# ── Server management ────────────────────────────────────────────────────


class Server:
    def __init__(self) -> None:
        self.port = find_free_port()
        self.api = f"http://127.0.0.1:{self.port}"
        self._proc: subprocess.Popen | None = None
        self._env = os.environ.copy()
        self._env.update(
            LUNA_API_HOST="127.0.0.1", LUNA_API_PORT=str(self.port), LUNA_MAX_STEPS="5", PYTHONUNBUFFERED="1"
        )

    def start(self) -> None:
        logger.info(f"Starting server on port {self.port} ...")
        python = sys.executable if ("UV_ACTIVE" in os.environ or sys.prefix != sys.base_prefix) else "uv run python"
        cmd = python.split() + ["api.py"]
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_DIR),
            env=self._env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
        self._wait_ready()

    def _wait_ready(self, timeout: int = 180) -> None:
        deadline = time.monotonic() + timeout
        up = False
        while time.monotonic() < deadline:
            if self._proc and self._proc.poll() is not None:
                raise RuntimeError("Server died during startup")
            try:
                if not up and requests.get(f"{self.api}/api/health", timeout=5).status_code == 200:
                    up = True
                if up:
                    s = requests.get(f"{self.api}/api/status", timeout=10).json()
                    if s.get("llm_ready") and s.get("ready"):
                        return
            except Exception:
                up = False
            time.sleep(0.3)
        raise TimeoutError("Server did not become ready")

    def stop(self) -> None:
        if not self._proc or self._proc.poll() is not None:
            return
        pgid = os.getpgid(self._proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            self._proc.wait(timeout=5)

    def server_pids(self) -> list[int]:
        """Return all PIDs belonging to the server process tree."""
        pids: list[int] = []
        if not self._proc:
            return pids
        main_pid = self._proc.pid
        pids.append(main_pid)
        try:
            out = subprocess.check_output(["pgrep", "-P", str(main_pid)], timeout=5).decode()
            for line in out.strip().splitlines():
                if line.strip():
                    pids.append(int(line.strip()))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        return pids


# ── Linux ps-based sampler ───────────────────────────────────────────────


class Sampler:
    """Samples CPU% and RSS (MB) of PIDs using ``ps`` every 0.5s."""

    def __init__(self, pids_fn):
        self._pids_fn = pids_fn
        self._samples: list[dict] = []
        self._stop = threading.Event()

    def start(self) -> None:
        self._stop.clear()
        self._samples.clear()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> list[dict]:
        self._stop.set()
        time.sleep(0.6)
        return list(self._samples)

    def _loop(self) -> None:
        while not self._stop.is_set():
            pids = self._pids_fn()
            if not pids:
                time.sleep(0.5)
                continue
            try:
                out = (
                    subprocess.check_output(
                        ["ps", "-p", ",".join(str(p) for p in pids), "-o", "%cpu=,rss=", "--no-header"],
                        timeout=5,
                        stderr=subprocess.DEVNULL,
                    )
                    .decode()
                    .strip()
                )
                total_cpu = 0.0
                total_rss = 0.0
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        total_cpu += float(parts[0])
                        total_rss += int(parts[1]) / 1024.0
                self._samples.append({"cpu": total_cpu, "ram_mb": total_rss, "ts": time.time()})
            except Exception:
                pass
            self._stop.wait(0.5)

    @property
    def stats(self) -> dict:
        if not self._samples:
            return {"avg_cpu": 0, "peak_cpu": 0, "avg_ram_mb": 0, "peak_ram_mb": 0}
        c = [s["cpu"] for s in self._samples]
        r = [s["ram_mb"] for s in self._samples]
        return {
            "avg_cpu": round(sum(c) / len(c), 1),
            "peak_cpu": round(max(c), 1),
            "avg_ram_mb": round(sum(r) / len(r), 1),
            "peak_ram_mb": round(max(r), 1),
        }


# ── Benchmark tasks ──────────────────────────────────────────────────────


def run_tasks(api: str) -> list[dict]:
    results = []

    def chat(msg: str) -> dict:
        t0 = time.monotonic()
        r = requests.post(f"{api}/api/chat", json={"message": msg, "voice": False}, timeout=300).json()
        dt = time.monotonic() - t0
        return {"time": round(dt, 2), "proc_ms": r.get("processing_time_ms", 0), "ok": True}

    def facts_add(text: str) -> dict:
        t0 = time.monotonic()
        r = requests.post(
            f"{api}/api/memory/facts", json={"fact": text, "category": "geral", "importance": 0.9}, timeout=10
        ).json()
        return {"time": round(time.monotonic() - t0, 2), "ok": r.get("success", False)}

    def facts_get(query: str = "") -> dict:
        t0 = time.monotonic()
        r = requests.get(f"{api}/api/memory/facts", params={"query": query}, timeout=10)
        return {"time": round(time.monotonic() - t0, 2), "ok": r.status_code == 200}

    tasks = [
        ("hello", lambda: chat("Hello Luna.")),
        ("what_can_you_do", lambda: chat("What can you do?")),
        ("save_memory", lambda: facts_add("My favorite color is blue.")),
        ("recall_memory", lambda: facts_get("favorite color")),
        ("execute_tool", lambda: chat("What time is it?")),
        ("planner", lambda: chat("Create a daily routine for a remote worker.")),
        (
            "reasoning",
            lambda: chat("If a train leaves at 9AM at 80km/h and another at 9:30AM at 100km/h, when do they meet?"),
        ),
    ]
    for name, fn in tasks:
        logger.info(f"  Task: {name} ...")
        try:
            r = fn()
            r["name"] = name
            r["error"] = ""
        except Exception as e:
            r = {"name": name, "time": 0, "ok": False, "error": str(e)[:120]}
        results.append(r)
    return results


# ── Report ───────────────────────────────────────────────────────────────


def print_report(info: dict, boot_s: float, samples: list[dict], tasks: list[dict], disk_mb: float) -> None:
    s = {"avg_cpu": 0, "peak_cpu": 0, "avg_ram_mb": 0, "peak_ram_mb": 0}
    if samples:
        c = [x["cpu"] for x in samples]
        r = [x["ram_mb"] for x in samples]
        s = {
            "avg_cpu": round(sum(c) / len(c), 1),
            "peak_cpu": round(max(c), 1),
            "avg_ram_mb": round(sum(r) / len(r), 1),
            "peak_ram_mb": round(max(r), 1),
        }

    passed = sum(1 for t in tasks if t["ok"])
    total = len(tasks)
    avg_resp = round(sum(t["time"] for t in tasks) / total, 2) if total else 0

    def sz(mb: float) -> str:
        return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{round(mb)} MB"

    print()
    print("=" * 52)
    print("  LUNA BENCHMARK REPORT")
    print("=" * 52)
    print(f"  System:      {info['os']}")
    print(f"  CPU:         {info['cpu']} ({info['cores']} cores)")
    print(f"  RAM:         {info['ram_gb']} GB")
    print()
    print("  \u2500\u2500 Metrics \u2500\u2500")
    print(f"  Boot Time:   {boot_s:.1f} s")
    print(f"  CPU Avg:     {s['avg_cpu']:.0f}%")
    print(f"  CPU Peak:    {s['peak_cpu']:.0f}%")
    print(f"  RAM Avg:     {sz(s['avg_ram_mb'])}")
    print(f"  RAM Peak:    {sz(s['peak_ram_mb'])}")
    print(f"  Disk:        {sz(disk_mb)}")
    print(f"  Avg Resp:    {avg_resp:.1f} s")
    print(f"  Passed:      {passed}/{total}")
    print()
    print("  \u2500\u2500 Tasks \u2500\u2500")
    for t in tasks:
        icon = "\u2713" if t["ok"] else "\u2717"
        extra = f"  error={t['error']}" if t.get("error") else ""
        print(f"  {icon} {t['name']:<18s} {t['time']:>7.2f}s{extra}")
    print()
    print("  \u2500\u2500 HW Recommendation \u2500\u2500")
    peak_ram = s["peak_ram_mb"] * 1.4
    if peak_ram < 900:
        mr, rr, ir_ = "1 GB", "2 GB", "4 GB"
    elif peak_ram < 1500:
        mr, rr, ir_ = "2 GB", "3 GB", "6 GB"
    elif peak_ram < 2500:
        mr, rr, ir_ = "3 GB", "4 GB", "8 GB"
    else:
        mr, rr, ir_ = "4 GB", "6 GB", "16 GB"

    peak_c = s["peak_cpu"]
    if peak_c < 30:
        mc, rc, ic_ = "1 core", "1 core", "2 cores"
    elif peak_c < 50:
        mc, rc, ic_ = "1 core", "2 cores", "4 cores"
    else:
        mc, rc, ic_ = "2 cores", "4 cores", "4+ cores"

    print(f"  {'':16s} {'CPU':16s} {'RAM':16s}")
    print(f"  {'Minimum':16s} {mc:16s} {mr:16s}")
    print(f"  {'Recommended':16s} {rc:16s} {rr:16s}")
    print(f"  {'Ideal':16s} {ic_:16s} {ir_:16s}")
    print()
    print("=" * 52)
    print()

    # JSON export
    json.dump(
        {
            "timestamp": datetime.now().isoformat(),
            "system": info,
            "boot_time_s": boot_s,
            "cpu_avg": s["avg_cpu"],
            "cpu_peak": s["peak_cpu"],
            "ram_avg_mb": s["avg_ram_mb"],
            "ram_peak_mb": s["peak_ram_mb"],
            "disk_mb": disk_mb,
            "avg_response_s": avg_resp,
            "tasks": tasks,
            "passed": passed,
            "total": total,
            "hw_minimum": {"cpu": mc, "ram": mr},
            "hw_recommended": {"cpu": rc, "ram": rr},
            "hw_ideal": {"cpu": ic_, "ram": ir_},
        },
        open("benchmark_results.json", "w"),
        indent=2,
    )
    logger.info("Results saved to benchmark_results.json")


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    print("\n  \u2554\u2550\u2550 Luna Hardware Benchmark \u2550\u2550\u2557\n")
    info = collect_system_info()
    logger.info(f"Host: {info['cpu']} ({info['cores']} cores, {info['ram_gb']} GB RAM)")

    server = Server()
    try:
        t0 = time.monotonic()
        server.start()
        boot = time.monotonic() - t0

        sampler = Sampler(server.server_pids)
        sampler.start()

        logger.info("Running tasks...")
        tasks = run_tasks(server.api)

        samples = sampler.stop()

    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        raise
    finally:
        server.stop()

    disk = disk_usage_mb()
    print_report(info, boot, samples, tasks, disk)


if __name__ == "__main__":
    main()
