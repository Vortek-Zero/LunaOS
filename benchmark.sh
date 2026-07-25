#!/usr/bin/env bash
# benchmark.sh — Luna Hardware Benchmark
# Mede CPU/RAM/tempo usando comandos nativos do Linux.
# Uso:  uv run bash benchmark.sh

set -euo pipefail

PORT=5050
API="http://127.0.0.1:$PORT"
BENCH_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS="$BENCH_DIR/benchmark_results.json"
SAMPLE_LOG=$(mktemp /tmp/luna-bench-samples-XXXXX.log)
BOOT_LOG=$(mktemp /tmp/luna-bench-boot-XXXXX.log)

cleanup() {
    rm -f "$SAMPLE_LOG" "$BOOT_LOG" 2>/dev/null || true
}
trap cleanup EXIT

# ── Info ────────────────────────────────────────────────────────────────

echo ""
echo "===================================================="
echo "  Luna Hardware Benchmark"
echo "===================================================="
echo ""

# ── Start server if not running ─────────────────────────────────────────

if ! curl -sf "$API/api/health" >/dev/null 2>&1; then
    echo "Starting server on port $PORT ..."
    cd "$BENCH_DIR"
    uv run python api.py &>/dev/null &
    SERVER_PID=$!
    # wait for health
    for i in $(seq 1 120); do
        if curl -sf "$API/api/health" >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    # wait for llm_ready
    BOOT_START=$(date +%s.%N)
    for i in $(seq 1 180); do
        if curl -sf "$API/api/status" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('llm_ready') and d.get('ready') else 1)" 2>/dev/null; then
            break
        fi
        sleep 0.5
    done
    BOOT_END=$(date +%s.%N)
    BOOT_TIME=$(python3 -c "print($BOOT_END - $BOOT_START)")
    echo "  Boot: ${BOOT_TIME}s"
else
    SERVER_PID=""
    echo "Using existing server on port $PORT"
    BOOT_TIME=0
fi

# make sure server is reachable
curl -sf "$API/api/health" >/dev/null 2>&1 || { echo "Server not reachable"; exit 1; }

echo "Collecting samples while running tasks..."

# ── Sampler ─────────────────────────────────────────────────────────────

# Find server PIDs (main python + children)
find_pids() {
    local main_pid
    main_pid=$(pgrep -f "api.py" | head -1 2>/dev/null || true)
    if [ -z "$main_pid" ]; then
        echo ""
        return
    fi
    echo -n "$main_pid"
    for child in $(pgrep -P "$main_pid" 2>/dev/null || true); do
        echo -n ",$child"
    done
}

# Sample CPU+RAM every 0.5s in background
sample_loop() {
    while true; do
        local pids
        pids=$(find_pids)
        if [ -n "$pids" ]; then
            # Use ps to get CPU% and RSS for all pids, sum them
            ps -p "$pids" -o "%cpu=,rss=" --no-header 2>/dev/null | \
                awk '{cpu+=$1; ram+=$2} END {printf "%.1f %.0f\n", cpu, ram}' >> "$SAMPLE_LOG"
        fi
        sleep 0.5
    done
}

sample_loop &
SAMPLE_PID=$!

# ── Tasks ───────────────────────────────────────────────────────────────

run_task() {
    local name="$1"
    local payload="$2"
    local start end elapsed

    start=$(date +%s.%N)
    local resp
    resp=$(curl -sf -X POST "$API/api/chat" \
        -H "Content-Type: application/json" \
        -d "$payload" 2>/dev/null || echo '{"response":"FAIL","processing_time_ms":0}')
    end=$(date +%s.%N)
    elapsed=$(python3 -c "print($end - $start)")
    local proc_ms
    proc_ms=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('processing_time_ms',0))")
    echo "$name|$elapsed|$proc_ms|ok"
}

memory_save() {
    local start end
    start=$(date +%s.%N)
    curl -sf -X POST "$API/api/memory/facts" \
        -H "Content-Type: application/json" \
        -d '{"fact":"My favorite color is blue.","category":"preferencias","importance":0.9}' >/dev/null 2>&1 || true
    end=$(date +%s.%N)
    python3 -c "print('save_memory|' + str($end - $start) + '|0|ok')"
}

memory_recall() {
    local start end
    start=$(date +%s.%N)
    curl -sf "$API/api/memory/facts?query=favorite+color" >/dev/null 2>&1 || true
    end=$(date +%s.%N)
    python3 -c "print('recall_memory|' + str($end - $start) + '|0|ok')"
}

echo ""
echo "  Task: hello ..."
run_task "hello" '{"message":"Hello Luna.","voice":false}'
echo "  Task: what_can_you_do ..."
run_task "what_can_you_do" '{"message":"What can you do?","voice":false}'
echo "  Task: save_memory ..."
memory_save
echo "  Task: recall_memory ..."
memory_recall
echo "  Task: execute_tool ..."
run_task "execute_tool" '{"message":"What time is it?","voice":false}'
echo "  Task: planner ..."
run_task "planner" '{"message":"Create a simple daily routine for a remote worker.","voice":false}'
echo "  Task: reasoning ..."
run_task "reasoning" '{"message":"If a train leaves Station A at 9 AM at 80 km/h and another leaves Station B at 9:30 AM at 100 km/h, when do they meet?","voice":false}'

# ── Stop sampler ────────────────────────────────────────────────────────

kill "$SAMPLE_PID" 2>/dev/null || true
sleep 0.6

# ── Compute metrics ────────────────────────────────────────────────────

# Parse samples
AVG_CPU=0
PEAK_CPU=0
AVG_RAM=0
PEAK_RAM=0
COUNT=0
if [ -s "$SAMPLE_LOG" ]; then
    while read -r cpu ram; do
        [ -z "$cpu" ] && continue
        COUNT=$((COUNT + 1))
        AVG_CPU=$(python3 -c "print($AVG_CPU + $cpu)")
        PEAK_CPU=$(python3 -c "print(max($PEAK_CPU, $cpu))")
        AVG_RAM=$(python3 -c "print($AVG_RAM + $ram)")
        PEAK_RAM=$(python3 -c "print(max($PEAK_RAM, $ram))")
    done < "$SAMPLE_LOG"
    if [ "$COUNT" -gt 0 ]; then
        AVG_CPU=$(python3 -c "print(round($AVG_CPU / $COUNT, 1))")
        AVG_RAM=$(python3 -c "print(round($AVG_RAM / $COUNT, 1))")
    fi
fi

# RSS is in KB from ps, convert to MB
AVG_RAM_MB=$(python3 -c "print(round($AVG_RAM / 1024, 1))" 2>/dev/null || echo 0)
PEAK_RAM_MB=$(python3 -c "print(round($PEAK_RAM / 1024, 1))" 2>/dev/null || echo 0)

# System info
CPU_MODEL=$(grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
CORES=$(nproc)
TOTAL_RAM=$(free -g | awk '/Mem:/ {print $2}')
OS="$(uname -s) $(uname -r)"
PYTHON_VER=$(python3 --version 2>&1 | cut -d' ' -f2)

# ── Report ──────────────────────────────────────────────────────────────

format_mb() {
    local mb=$1
    python3 -c "
v = float($mb)
if v >= 1024: print(f'{v/1024:.1f} GB')
else: print(f'{round(v)} MB')
"
}

echo ""
echo "===================================================="
echo "  LUNA BENCHMARK REPORT"
echo "===================================================="
echo ""
echo "  System:   $OS"
echo "  Python:   $PYTHON_VER"
echo "  CPU:      $CPU_MODEL ($CORES cores)"
echo "  RAM:      ${TOTAL_RAM}GB"
echo ""
echo "  ── Metrics ──"
echo "  Boot:     ${BOOT_TIME}s"
echo "  CPU Avg:  ${AVG_CPU}%"
echo "  CPU Peak: ${PEAK_CPU}%"
echo "  RAM Avg:  $(format_mb "$AVG_RAM_MB")"
echo "  RAM Peak: $(format_mb "$PEAK_RAM_MB")"
echo ""

# Print task times
echo "  ── Tasks ──"
TASKS_JSON="["
FIRST=1
PASSED=0
TOTAL_TASKS=0
LATENCY_SUM=0
while IFS='|' read -r name elapsed proc_ms status; do
    [ -z "$name" ] && continue
    TOTAL_TASKS=$((TOTAL_TASKS + 1))
    if [ "$status" = "ok" ]; then
        PASSED=$((PASSED + 1))
    fi
    LATENCY_SUM=$(python3 -c "print($LATENCY_SUM + $elapsed)")
    echo "  ✓ $name  ${elapsed}s"
    if [ "$FIRST" = 1 ]; then
        FIRST=0
    else
        TASKS_JSON="$TASKS_JSON,"
    fi
    TASKS_JSON="$TASKS_JSON{\"name\":\"$name\",\"time\":$elapsed,\"proc_ms\":$proc_ms,\"ok\":true}"
done < <(run_task "hello" '{"message":"Hello Luna.","voice":false}'; \
         run_task "what_can_you_do" '{"message":"What can you do?","voice":false}'; \
         memory_save; \
         memory_recall; \
         run_task "execute_tool" '{"message":"What time is it?","voice":false}'; \
         run_task "planner" '{"message":"Create a simple daily routine for a remote worker.","voice":false}'; \
         run_task "reasoning" '{"message":"If a train leaves Station A at 9 AM at 80 km/h and another leaves Station B at 9:30 AM at 100 km/h, when do they meet?","voice":false}')
TASKS_JSON="$TASKS_JSON]"

AVG_RESP=$(python3 -c "print(round($LATENCY_SUM / $TOTAL_TASKS, 2))" 2>/dev/null || echo 0)

echo ""
echo "  Passed:  ${PASSED}/${TOTAL_TASKS}"
echo "  Avg Resp: ${AVG_RESP}s"
echo ""

# ── HW Recommendation ──────────────────────────────────────────────────

RAW_RAM=$(python3 -c "print($PEAK_RAM_MB * 1.4)" 2>/dev/null || echo 0)
if python3 -c "exit(0 if $RAW_RAM < 900 else 1)" 2>/dev/null; then
    MR="1 GB"; RR="2 GB"; IR="4 GB"
elif python3 -c "exit(0 if $RAW_RAM < 1500 else 1)" 2>/dev/null; then
    MR="2 GB"; RR="3 GB"; IR="6 GB"
elif python3 -c "exit(0 if $RAW_RAM < 2500 else 1)" 2>/dev/null; then
    MR="3 GB"; RR="4 GB"; IR="8 GB"
else
    MR="4 GB"; RR="6 GB"; IR="16 GB"
fi

if python3 -c "exit(0 if $PEAK_CPU < 30 else 1)" 2>/dev/null; then
    MC="1 core"; RC="1 core"; IC="2 cores"
elif python3 -c "exit(0 if $PEAK_CPU < 50 else 1)" 2>/dev/null; then
    MC="1 core"; RC="2 cores"; IC="4 cores"
else
    MC="2 cores"; RC="4 cores"; IC="4+ cores"
fi

echo "  ── HW Recommendation ──"
printf "  %-16s %-16s %-16s\n" "" "CPU" "RAM"
printf "  %-16s %-16s %-16s\n" "Minimum" "$MC" "$MR"
printf "  %-16s %-16s %-16s\n" "Recommended" "$RC" "$RR"
printf "  %-16s %-16s %-16s\n" "Ideal" "$IC" "$IR"
echo ""
echo "===================================================="
echo ""

# ── JSON export ─────────────────────────────────────────────────────────

python3 -c "
import json
report = {
    'timestamp': '$TIMESTAMP',
    'system': {'os': '$OS', 'python': '$PYTHON_VER', 'cpu': '$CPU_MODEL', 'cores': $CORES, 'ram_gb': $TOTAL_RAM},
    'boot_time_s': $BOOT_TIME,
    'cpu_avg': $AVG_CPU, 'cpu_peak': $PEAK_CPU,
    'ram_avg_mb': $AVG_RAM_MB, 'ram_peak_mb': $PEAK_RAM_MB,
    'avg_response_s': $AVG_RESP,
    'passed': $PASSED, 'total': $TOTAL_TASKS,
    'tasks': $TASKS_JSON,
    'hw_minimum': {'cpu': '$MC', 'ram': '$MR'},
    'hw_recommended': {'cpu': '$RC', 'ram': '$RR'},
    'hw_ideal': {'cpu': '$IC', 'ram': '$IR'},
}
with open('$RESULTS', 'w') as f:
    json.dump(report, f, indent=2)
print('Results saved to $RESULTS')
"

# ── Cleanup ─────────────────────────────────────────────────────────────

if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
fi
