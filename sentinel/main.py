"""
SentinelArena -- Phase 1 PoC Entry Point

Runs the full Red vs Blue arena with a rich terminal UI.
Shows live agent reasoning, OPA decisions, battle feed, and attack surface score.

Usage:
    python main.py               # Full 8-round arena
    python main.py --rounds 3    # Quick 3-round demo
    python main.py --reset       # Reset memory and start fresh
"""
import sys
import os
os.environ["AIRA_LIVE_SCAN"] = "false"
import argparse
import time
from datetime import datetime

# Force UTF-8 output -- prevents Windows cp1252 UnicodeEncodeError
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add poc directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich import box
from rich.align import Align

from config import settings
from memory import load_memory, empty_memory, init_new_session
from graph.arena_graph import build_arena_graph, create_initial_state

# Force rich to use UTF-8 safe rendering
console = Console(highlight=False)

BANNER = r"""
  ____  _____ _   _ _____ ___ _   _ _____ _       _    ____  _____ _   _    _
 / ___|| ____| \ | |_   _|_ _| \ | | ____| |     / \  |  _ \| ____| \ | |  / \
 \___ \|  _| |  \| | | |  | ||  \| |  _| | |    / _ \ | |_) |  _| |  \| | / _ \
  ___) | |___| |\  | | |  | || |\  | |___| |___ / ___ \|  _ <| |___| |\  |/ ___ \
 |____/|_____|_| \_| |_| |___|_| \_|_____|_____/_/   \_\_| \_\_____|_| \_/_/   \_\
"""

SUBTITLE = "Autonomous Red vs Blue AI Defense System  |  Phase 1: PoC"


# -----------------------------------------------------------------------------
# Terminal UI Helpers
# -----------------------------------------------------------------------------

def render_score_bar(score: float, width: int = 40) -> Text:
    """Render a color-graded attack surface score bar using safe ASCII chars."""
    filled = int((score / 100) * width)
    empty = width - filled
    bar = Text()
    color = "red" if score > 70 else "yellow" if score > 40 else "green"
    bar.append("#" * filled, style=f"bold {color}")
    bar.append("-" * empty, style="dim white")
    return bar


def render_event(event: dict) -> Text:
    """Color-code an arena event for the battle feed."""
    agent    = event.get("agent", "system")
    msg      = event.get("message", "")
    ts       = event.get("timestamp", "")[:19].replace("T", " ")

    agent_cfg = {
        "red":          ("[RED]", "bold red"),
        "blue":         ("[BLU]", "bold cyan"),
        "orchestrator": ("[OPA]", "bold yellow"),
        "system":       ("[SYS]", "bold white"),
    }
    tag, style = agent_cfg.get(agent, ("[???]", "white"))

    t = Text()
    t.append(f"[{ts}] ", style="dim white")
    t.append(f"{tag} ", style=style)
    t.append(msg, style=style if "kill_switch" in event.get("event_type", "") else "white")
    return t


def render_summary_table(state: dict) -> Table:
    """Render the per-round battle summary table."""
    table = Table(
        title="[bold]Battle Summary[/bold]",
        box=box.ROUNDED,
        border_style="dim white",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Round",       style="dim",  width=7)
    table.add_column("Red Action",  style="red",  width=20)
    table.add_column("OPA",         style="yellow", width=8)
    table.add_column("Blue Defense",style="cyan", width=22)
    table.add_column("Score D",     width=10)
    table.add_column("Score",       width=8)

    attacks       = state.get("attacks", [])
    defenses      = state.get("defenses", [])
    score_history = state.get("score_history", [])

    for i, attack in enumerate(attacks):
        defense      = defenses[i] if i < len(defenses) else {}
        score        = score_history[i + 1] if i + 1 < len(score_history) else 0.0
        score_before = score_history[i]      if i     < len(score_history) else 0.0
        delta        = round(float(score) - float(score_before), 1)

        opa          = attack.get("opa_decision", "?")
        opa_style    = "green" if opa == "allowed" else "red"
        delta_str    = f"{delta:+.1f}"
        delta_style  = "green" if delta < 0 else "red"

        table.add_row(
            str(attack.get("round", i + 1)),
            attack.get("vuln_type", "?")[:20],
            Text(opa[:7], style=opa_style),
            defense.get("defense_type", "--")[:22],
            Text(delta_str, style=delta_style),
            f"{score:.1f}",
        )
    return table


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SentinelArena Phase 1 PoC")
    parser.add_argument("--rounds", type=int, default=settings.MAX_ROUNDS,
                        help=f"Number of rounds (default: {settings.MAX_ROUNDS})")
    parser.add_argument("--reset", action="store_true",
                        help="Reset memory and start fresh")
    args = parser.parse_args()

    # Validate API key
    try:
        settings.validate()
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        sys.exit(1)

    # Banner
    console.print(Text(BANNER, style="bold red"))
    console.print(Align.center(Text(SUBTITLE, style="bold white")))
    console.print(Align.center(Text(
        f"Model: {settings.GEMINI_MODEL}  |  Rounds: {args.rounds}  |  "
        f"Blast Radius Limit: {settings.BLAST_RADIUS_LIMIT}",
        style="dim cyan",
    )))
    console.print()

    # Load memory
    if args.reset:
        memory = empty_memory()
        console.print("[yellow]Memory reset -- starting fresh[/yellow]")
    else:
        prev_mem = load_memory()
        memory = init_new_session(prev_mem)
        if memory.get("patched_resources") or memory.get("red_learned"):
            console.print(f"[cyan]Loaded active memory (Session: {memory.get('arena_id')})[/cyan]")
            console.print(f"  * Patched resources: {len(memory.get('patched_resources', []))}")
            console.print(f"  * Learned attack rules: {len(memory.get('red_learned', []))}")
        else:
            console.print("[dim]Starting with empty memory (round 1)[/dim]")

    console.print()
    console.print(Rule("[bold red][ RED AGENT ][/bold red] vs "
                       "[bold cyan][ BLUE AGENT ][/bold cyan]  |  "
                       "[bold yellow][ SAFETY ORCHESTRATOR ][/bold yellow]"))
    console.print()
    time.sleep(0.5)

    # Build LangGraph
    console.print("[dim]Building LangGraph agent graph...[/dim]")
    arena         = build_arena_graph()
    initial_state = create_initial_state(memory, max_rounds=args.rounds)

    initial_score = initial_state["attack_surface_score"]
    vuln_count    = len(initial_state["vulnerabilities"])

    console.print()
    console.print(Panel(
        f"[bold red]Attack Surface Score: {initial_score}/100[/bold red]  |  "
        f"[yellow]Vulnerabilities: {vuln_count}[/yellow]  |  "
        f"[cyan]Rounds: {args.rounds}[/cyan]",
        title="[bold]ARENA INITIALIZED[/bold]",
        border_style="red",
    ))
    console.print()
    time.sleep(0.5)

    # Stream graph
    console.print("[bold white]Starting arena...[/bold white]")
    console.print(Rule(style="dim"))

    accumulated_state    = dict(initial_state)
    displayed_event_count = 0

    try:
        for step_output in arena.stream(initial_state, {"recursion_limit": 150}):
            for node_name, node_state in step_output.items():
                # Merge node updates into our accumulated state
                for k, v in node_state.items():
                    accumulated_state[k] = v

                events = node_state.get("events", [])

                # Print new events
                for event in events[displayed_event_count:]:
                    console.print(render_event(event))
                displayed_event_count = max(displayed_event_count, len(events))

                # Score bar after Blue runs
                if "attack_surface_score" in node_state and node_name == "blue_agent":
                    score = node_state["attack_surface_score"]
                    bar   = render_score_bar(score)
                    t = Text()
                    t.append("\n  Attack Surface Score: ", style="bold white")
                    color = "bold red" if score > 70 else "bold yellow" if score > 40 else "bold green"
                    t.append(f"{score:5.1f}/100  ", style=color)
                    t.append(bar)
                    console.print(t)
                    console.print()

                if node_name == "memory_update":
                    console.print(Rule(style="dim"))

        final_state = accumulated_state

    except KeyboardInterrupt:
        console.print("\n[yellow]Arena interrupted.[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Arena error: {e}[/bold red]")
        import traceback
        traceback.print_exc()

    # Final report
    console.print()
    console.print(Rule("[bold]FINAL REPORT[/bold]"))
    console.print()

    if final_state:
        final_score     = final_state.get("attack_surface_score", 0)
        score_reduction = round(initial_score - final_score, 1)
        total_attacks   = len(final_state.get("attacks", []))
        total_defenses  = len(final_state.get("defenses", []))
        opa_blocks      = sum(1 for d in final_state.get("opa_decisions", [])
                              if d.get("decision") == "DENY")

        # Score summary panel
        grade = "HARDENED" if final_score < 30 else "IMPROVED" if final_score < 60 else "EXPOSED"
        console.print(Panel(
            Align.center(Text(
                f"[{grade}]  {initial_score} --> {final_score}  "
                f"({-score_reduction:+.1f} attack surface reduction)",
                style="bold white",
            )),
            title="[bold]Attack Surface Score[/bold]",
            border_style="green" if final_score < 30 else "yellow" if final_score < 60 else "red",
        ))
        console.print()

        # Stats
        stats = Table(box=box.ROUNDED, border_style="dim white", show_header=False)
        stats.add_column("Metric", style="bold white")
        stats.add_column("Value",  style="cyan")
        stats.add_row("Total Rounds",          str(final_state.get("round", 1) - 1))
        stats.add_row("Red Attacks Launched",  str(total_attacks))
        stats.add_row("Blue Defenses Applied", str(total_defenses))
        stats.add_row("OPA Blocks",            f"[yellow]{opa_blocks}[/yellow]")
        stats.add_row("Kill Switch Triggered",
                      "[red]YES[/red]" if final_state.get("kill_switch") else "[green]NO[/green]")
        stats.add_row("Score Reduction",
                      f"[green]{score_reduction:.1f} points[/green]")
        console.print(stats)
        console.print()

        # Round table
        console.print(render_summary_table(final_state))
        console.print()

        # Learning panels
        mem = final_state.get("memory", {})
        if mem.get("red_learned"):
            console.print(Panel(
                "\n".join(f"  * {item}" for item in mem["red_learned"][-6:]),
                title="[bold red]Red Agent Learned[/bold red]",
                border_style="red",
            ))
        if mem.get("patched_resources"):
            console.print(Panel(
                "\n".join(f"  + {r}" for r in mem["patched_resources"][-8:]),
                title="[bold cyan]Blue Agent Hardened[/bold cyan]",
                border_style="cyan",
            ))

    console.print()
    console.print(Align.center(Text(
        "Memory saved --> memory_store/battle_memory.json  |  "
        "Run again to see adaptive learning",
        style="dim",
    )))
    console.print()


if __name__ == "__main__":
    main()
