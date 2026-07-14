#!/usr/bin/env python3
"""
scripts/luna_debug.py — Painel de Debug em tempo real da Luna v1.4.1
Exibe métricas de cognição, memória e uso de ferramentas.
"""
import sys
import time
from pathlib import Path

# Add project root to path so we can import brain modules
sys.path.append(str(Path(__file__).parent.parent))

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    from rich.live import Live
except ImportError:
    print("Por favor, instale a biblioteca 'rich' para ver o dashboard: pip install rich")
    sys.exit(1)

from brain.metrics_aggregator import get_metrics_aggregator

console = Console()

def generate_dashboard() -> Layout:
    aggregator = get_metrics_aggregator()
    metrics = aggregator.get_dashboard_metrics()
    
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main")
    )
    layout["main"].split_row(
        Layout(name="left"),
        Layout(name="right")
    )
    layout["left"].split_column(
        Layout(name="cognition", size=10),
        Layout(name="memory")
    )
    layout["right"].split_column(
        Layout(name="tools", size=10),
        Layout(name="performance")
    )

    # HEADER
    layout["header"].update(Panel("🌙 [bold magenta]LUNA DEBUG DASHBOARD[/] (v1.4.1 Stabilization)", style="white on blue"))

    # COGNITION
    cog_table = Table(box=box.SIMPLE, show_header=False)
    cog_table.add_column("Item", style="cyan")
    cog_table.add_column("Value", style="green")
    
    planner = metrics.get("planner", {})
    cog_table.add_row("Planner Success", f"[bold green]✓ {planner.get('success_rate', 0)}%[/] ({planner.get('success')}/{planner.get('total')})")
    
    reflection = metrics.get("reflection", {})
    cog_table.add_row("Reflection Efficiency", f"[bold green]✓ {reflection.get('success_rate', 0)}%[/] ({reflection.get('success')}/{reflection.get('total')})")
    
    layout["cognition"].update(Panel(cog_table, title="🧠 [bold]Cognitive Engine", border_style="cyan"))

    # TOOLS
    tools_table = Table(box=box.SIMPLE)
    tools_table.add_column("Tool", style="magenta")
    tools_table.add_column("Calls", justify="right", style="green")
    
    tools = metrics.get("tools", {})
    if not tools:
        tools_table.add_row("Nenhuma ferramenta recente", "")
    for t_name, t_count in tools.items():
        tools_table.add_row(t_name, str(t_count))
        
    layout["tools"].update(Panel(tools_table, title="🛠️ [bold]Tool Execution (Top 5)", border_style="magenta"))

    # MEMORY
    mem_table = Table(box=box.SIMPLE, show_header=False)
    mem_table.add_column("Item", style="yellow")
    mem_table.add_column("Value", style="bold white")
    
    memory = metrics.get("memory", {})
    mem_table.add_row("Episodes", str(memory.get('episodes', 0)))
    mem_table.add_row("Profile Items", str(memory.get('profile_items', 0)))
    mem_table.add_row("Active Goals", str(memory.get('goals', 0)))
    
    layout["memory"].update(Panel(mem_table, title="📦 [bold]Hierarchical Memory", border_style="yellow"))

    # PERFORMANCE
    perf_table = Table(box=box.SIMPLE, show_header=False)
    perf_table.add_column("Item", style="blue")
    perf_table.add_column("Value", style="bold white")
    
    perf = metrics.get("performance", {})
    perf_table.add_row("Average Latency", f"{perf.get('avg_latency', 0.0)} s")
    perf_table.add_row("Total Traces Analyzed", str(perf.get('total_traces', 0)))
    
    layout["performance"].update(Panel(perf_table, title="⚡ [bold]Performance Profiling", border_style="blue"))

    return layout

if __name__ == "__main__":
    try:
        with Live(generate_dashboard(), refresh_per_second=1, screen=True) as live:
            while True:
                time.sleep(1)
                live.update(generate_dashboard())
    except KeyboardInterrupt:
        console.print("[bold red]Debug encerrado.[/]")
        sys.exit(0)
