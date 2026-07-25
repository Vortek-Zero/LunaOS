#!/usr/bin/env python3
"""Benchmark relâmpago da Luna — 2 tasks, CPU/RAM via ps."""

import json
import os
import subprocess
import threading
import time
import urllib.request

API = "http://127.0.0.1:5050"
LOG = "/tmp/luna_samples.log"

# ── Sampler ─────────────────────────────────────────────────────────────

SAMPLE_LOG = []


def find_pids():
    try:
        pids = subprocess.check_output(["pgrep", "-f", "api.py"], text=True).strip().split("\n")
        pids = [p for p in pids if p.strip()]
    except Exception:
        return ""
    return ",".join(pids)


def sampler_thread(stop_event):
    while not stop_event.is_set():
        pids = find_pids()
        if pids:
            try:
                out = subprocess.check_output(
                    ["ps", "-p", pids, "-o", "%cpu=,rss=", "--no-header"], text=True, timeout=3
                )
                total_cpu = 0.0
                total_rss = 0
                for line in out.strip().split("\n"):
                    line = line.strip()
                    if line:
                        parts = line.split()
                        if len(parts) >= 2:
                            total_cpu += float(parts[0])
                            total_rss += int(parts[1])
                if total_rss > 0:
                    SAMPLE_LOG.append((total_cpu, total_rss))
            except Exception:
                pass
        time.sleep(0.5)


# ── API helper ──────────────────────────────────────────────────────────


def api_post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{API}{path}", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def api_get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=10) as resp:
        return json.loads(resp.read())


# ── Main ────────────────────────────────────────────────────────────────


def main():
    print()
    print("=" * 52)
    print("  Luna Benchmark Relâmpago")
    print("=" * 52)
    print()

    # Health check
    try:
        health = api_get("/api/health")
        print(f"  Server: {health['status']} v{health['version']}")
    except Exception as e:
        print(f"  Server DOWN: {e}")
        return 1

    status = api_get("/api/status")
    if not status.get("llm_ready"):
        print("  Waiting for LLM...")
        for _ in range(120):
            time.sleep(1)
            status = api_get("/api/status")
            if status.get("llm_ready"):
                break

    boot_took = status.get("boot_time_ms", 0) / 1000
    print(f"  Boot: {boot_took:.1f}s")
    print()

    # Start sampler
    stop = threading.Event()
    t = threading.Thread(target=sampler_thread, args=(stop,), daemon=True)
    t.start()

    tasks = [
        ("hello", {"message": "Hello Luna.", "voice": False}),
        ("time", {"message": "What time is it?", "voice": False}),
    ]

    results = []
    for name, payload in tasks:
        print(f"  Task: {name} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            resp = api_post("/api/chat", payload)
            elapsed = time.time() - t0
            proc_ms = resp.get("processing_time_ms", 0)
            results.append((name, elapsed, proc_ms, True))
            print(f"{elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - t0
            results.append((name, elapsed, 0, False))
            print(f"FAIL ({e})")

    # Stop sampler
    stop.set()
    time.sleep(0.6)

    # Compute metrics
    total_cpu = 0.0
    peak_cpu = 0.0
    total_ram = 0
    peak_ram = 0
    count = len(SAMPLE_LOG)
    for cpu, rss in SAMPLE_LOG:
        total_cpu += cpu
        peak_cpu = max(peak_cpu, cpu)
        total_ram += rss
        peak_ram = max(peak_ram, rss)

    avg_cpu = round(total_cpu / count, 1) if count else 0.0
    avg_ram_kb = total_ram / count if count else 0
    avg_ram_mb = round(avg_ram_kb / 1024, 1)
    peak_ram_mb = round(peak_ram / 1024, 1)

    # System info
    cpu_model = "?"
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu_model = line.split(":")[1].strip()
                    break
    except Exception:
        pass
    cores = os.cpu_count() or 0
    total_ram_gb = 0
    try:
        out = subprocess.check_output(["free", "-g"], text=True)
        for line in out.split("\n"):
            if line.startswith("Mem:"):
                total_ram_gb = int(line.split()[1])
    except Exception:
        pass

    # Format RAM with nice units
    def fmt_mb(mb):
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        return f"{round(mb)} MB"

    # HW recommendation
    safe_ram = peak_ram / 1024 * 1.4
    if safe_ram < 900:
        mr, rr, ir = "1 GB", "2 GB", "4 GB"
    elif safe_ram < 1500:
        mr, rr, ir = "2 GB", "3 GB", "6 GB"
    elif safe_ram < 2500:
        mr, rr, ir = "3 GB", "4 GB", "8 GB"
    else:
        mr, rr, ir = "4 GB", "6 GB", "16 GB"

    if peak_cpu < 30:
        mc, rc, ic = "1 core", "1 core", "2 cores"
    elif peak_cpu < 50:
        mc, rc, ic = "1 core", "2 cores", "4 cores"
    else:
        mc, rc, ic = "2 cores", "4 cores", "4+ cores"

    print()
    print("=" * 52)
    print("  RELATÓRIO")
    print("=" * 52)
    print()
    print(f"  CPU:     {cpu_model} ({cores} cores)")
    print(f"  RAM:     {total_ram_gb} GB")
    print(f"  Boot:    {boot_took:.1f}s")
    print(f"  CPU Avg: {avg_cpu}%")
    print(f"  CPU Pk:  {peak_cpu}%")
    print(f"  RAM Avg: {fmt_mb(avg_ram_mb)}")
    print(f"  RAM Pk:  {fmt_mb(peak_ram_mb)}")
    print()
    for name, elapsed, _, ok in results:
        print(f"  {'✓' if ok else '✗'} {name:<12} {elapsed:.1f}s")
    avg_resp = sum(r[1] for r in results) / len(results)
    print(f"\n  Avg Resp: {avg_resp:.1f}s")
    print(f"  Samples:  {count}")
    print()
    print(f"  HW Min:     CPU {mc}, RAM {mr}")
    print(f"  HW Rec:     CPU {rc}, RAM {rr}")
    print(f"  HW Ideal:   CPU {ic}, RAM {ir}")
    print()
    print("=" * 52)

    # Save JSON
    report = {
        "system": {"cpu": cpu_model, "cores": cores, "ram_gb": total_ram_gb},
        "boot_time_s": boot_took,
        "cpu_avg": avg_cpu,
        "cpu_peak": peak_cpu,
        "ram_avg_mb": avg_ram_mb,
        "ram_peak_mb": peak_ram_mb,
        "avg_response_s": round(avg_resp, 1),
        "tasks": [{"name": n, "time": t} for n, t, _, _ in results],
        "hw_minimum": {"cpu": mc, "ram": mr},
        "hw_recommended": {"cpu": rc, "ram": rr},
        "hw_ideal": {"cpu": ic, "ram": ir},
    }
    with open("benchmark_results.json", "w") as f:
        json.dump(report, f, indent=2)
    print("  → benchmark_results.json")
    print()

    return 0


if __name__ == "__main__":
    exit(main())
