import shutil
import subprocess
import sys

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()
ACCENT = "magenta"


def warn(msg):
    console.print(f"[yellow]![/] {msg}")


def error(msg):
    console.print(f"[bold red]error:[/] {msg}")


def _pager(items, label):
    """Full-screen picker used when fzf is missing: filter by typing, number to select."""
    page, q = 0, ""
    with console.screen():
        while True:
            view = [(i, t) for i, (t, _) in enumerate(items, 1) if q.lower() in t.lower()]
            size = max(5, console.size.height - 9)
            pages = max(1, -(-len(view) // size))
            page = min(page, pages - 1)
            console.clear()
            console.print(Panel(f"[bold]{label}[/]   filter: [cyan]{q or '-'}[/]   page {page + 1}/{pages}",
                                border_style=ACCENT, box=box.ROUNDED))
            table = Table(box=box.SIMPLE_HEAD, border_style=ACCENT, header_style="bold cyan")
            table.add_column("#", justify="right", style="dim")
            table.add_column(label)
            for i, t in view[page * size:(page + 1) * size]:
                table.add_row(str(i), t)
            console.print(table)
            console.print("[dim]number: select  |  text: filter  |  enter: clear filter  |  n/p: page  |  q: cancel[/]")
            cmd = Prompt.ask(">").strip()
            if cmd.isdigit() and any(i == int(cmd) for i, _ in view):
                return items[int(cmd) - 1][1]
            if cmd == "n":
                page += 1
            elif cmd == "p":
                page = max(0, page - 1)
            elif cmd == "q":
                sys.exit(0)
            else:
                q, page = cmd, 0


def pick(items, label):
    """items: list of (text, value). Opens a full-screen picker and returns the chosen value."""
    if not items:
        error("nothing found")
        sys.exit(1)
    if shutil.which("fzf"):
        lines = [f"{i}\t{t}" for i, (t, _) in enumerate(items)]
        p = subprocess.run(
            ["fzf", "--with-nth=2..", "--delimiter=\t", "--layout=reverse", "--border=rounded",
             "--cycle", "--info=inline", f"--prompt={label} > ",
             f"--header={label}   enter: select   esc: cancel   type to filter",
             "--preview=echo {2..}", "--preview-window=down:3:wrap:border-rounded",
             "--color=hl:magenta,hl+:magenta,pointer:cyan,prompt:cyan,border:magenta,header:dim"],
            input="\n".join(lines), text=True, stdout=subprocess.PIPE)
        if not p.stdout.strip():
            sys.exit(0)
        return items[int(p.stdout.split("\t")[0])][1]
    return _pager(items, label)
