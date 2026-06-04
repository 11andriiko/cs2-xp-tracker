import json
import datetime
from pathlib import Path
import typer
from rich import print
from rich.table import Table
from rich.panel import Panel
from rich.console import Console

try:
    from prompt_toolkit import prompt as pt_prompt
    USE_PROMPT_TOOLKIT = True
except ImportError:
    USE_PROMPT_TOOLKIT = False

app = typer.Typer()
console = Console()

DATA_FILE = Path("cs2xp.json")

# ─────────────────────────────
# CONSTANTS
# ─────────────────────────────

XP_PER_RANK = 5000
RANKS_MEDAL = 39
XP_PER_MEDAL = XP_PER_RANK * RANKS_MEDAL

BASIC_4X = 1125
BASIC_2X = 1500
BASIC_1X = 3667
BASIC_CAP = BASIC_4X + BASIC_2X + BASIC_1X

REDUCED_MULT = 0.175

MISSION_CYCLE = [600, 1050, 1050, 550, 1050, 1050, 600, 1050]
FIRST_WED = datetime.date(2026, 1, 7)

DM_XP = 75
COMP_XP = 390
DM_TIME = 10
COMP_TIME = 30

# ─────────────────────────────
# STORAGE
# ─────────────────────────────

def load():
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())

def save(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))

# ─────────────────────────────
# TIME
# ─────────────────────────────

def week_now():
    now = datetime.datetime.now(datetime.UTC)
    shifted = now - datetime.timedelta(hours=1)
    return max(1, (shifted.date() - FIRST_WED).days // 7 + 1)

def get_week_dates(week):
    start = FIRST_WED + datetime.timedelta(days=(week - 1) * 7)
    end = start + datetime.timedelta(days=6)
    return start.isoformat(), end.isoformat()

def mission_max(week):
    return MISSION_CYCLE[(week - 1) % 8]

# ─────────────────────────────
# XP
# ─────────────────────────────

def to_abs(medal, rank, xp):
    return medal * XP_PER_MEDAL + (rank - 1) * XP_PER_RANK + xp

def reverse_basic_from_total(total_xp):
    if total_xp <= BASIC_4X * 4:
        return total_xp / 4

    if total_xp <= BASIC_4X * 4 + BASIC_2X * 2:
        return BASIC_4X + (total_xp - BASIC_4X * 4) / 2

    if total_xp <= BASIC_4X * 4 + BASIC_2X * 2 + BASIC_1X:
        return BASIC_4X + BASIC_2X + (total_xp - (BASIC_4X * 4 + BASIC_2X * 2))

    base_total = BASIC_4X * 4 + BASIC_2X * 2 + BASIC_1X
    extra = total_xp - base_total

    return BASIC_CAP + extra / REDUCED_MULT

def compute_xp(basic):
    if basic <= BASIC_4X:
        return basic * 4, 0, "4x"

    if basic <= BASIC_4X + BASIC_2X:
        return BASIC_4X * 4 + (basic - BASIC_4X) * 2, 0, "2x"

    if basic <= BASIC_CAP:
        return BASIC_4X * 4 + BASIC_2X * 2 + (basic - BASIC_4X - BASIC_2X), 0, "1x"

    base_total = BASIC_4X * 4 + BASIC_2X * 2 + BASIC_1X
    extra = basic - BASIC_CAP
    reduced = extra * REDUCED_MULT

    return base_total + reduced, reduced, "0.175x"

def bar(cur, maxv, length=20):
    if maxv == 0:
        return ""
    r = min(cur / maxv, 1)
    f = int(r * length)
    return "█" * f + "░" * (length - f)

# ─────────────────────────────
# WEEK INIT
# ─────────────────────────────

def ensure_week_exists(data, week):
    w = str(week)

    if w in data:
        return data

    prev = data.get(str(week - 1))

    if prev:
        base_abs = prev["abs_xp"]
        rank, xp, medal = prev["rank"], prev["xp"], prev["medal"]
    else:
        base_abs = 0
        rank, xp, medal = 0, 0, 0

    start, end = get_week_dates(week)

    data[w] = {
        "abs_xp": base_abs,
        "rank": rank,
        "xp": xp,
        "medal": medal,
        "basic_xp": 0,
        "reduced_xp": 0,
        "mission_actual": 0,
        "mission_max": mission_max(week),
        "date_start": start,
        "date_end": end
    }

    save(data)
    return data

# ─────────────────────────────
# STATUS
# ─────────────────────────────

@app.command()
def status():
    data = load()
    w = week_now()
    data = ensure_week_exists(data, w)

    row = data[str(w)]
    prev = data.get(str(w - 1), row)

    gained_total = (row["abs_xp"] - prev["abs_xp"]) - row["mission_actual"]
    basic = row["basic_xp"]

    total, reduced, stage = compute_xp(basic)

    # thresholds
    t4 = BASIC_4X
    t2 = BASIC_4X + BASIC_2X
    t1 = BASIC_CAP

    # remaining
    rem4 = max(0, t4 - basic)
    rem2 = max(0, t2 - basic)
    rem1 = max(0, t1 - basic)

    # %
    p4 = basic / t4 * 100 if t4 else 0
    p2 = basic / t2 * 100 if t2 else 0
    p1 = basic / t1 * 100 if t1 else 0

    # mission
    m_cur = row["mission_actual"]
    m_max = row["mission_max"]
    m_pct = (m_cur / m_max * 100) if m_max else 0

    # games
    dm_played = basic / DM_XP
    comp_played = basic / COMP_XP

    dm_need = rem1 / DM_XP
    comp_need = rem1 / COMP_XP

    # rank
    xp_to_rank = XP_PER_RANK - row["xp"]

    console.print(Panel.fit(f"[bold cyan]Week {w}[/bold cyan]"))

    console.print(f"\n[green]Stage:[/green] {stage}")

    console.print("\n[bold]Basic XP[/bold]")
    console.print(f"{basic:.0f}/{t1} ({p1:.1f}%) {bar(basic, t1)}")

    console.print("\n[bold]Mission[/bold]")
    console.print(f"{m_cur}/{m_max} ({m_pct:.1f}%) {bar(m_cur, m_max)}")

    console.print("\n[bold]Thresholds[/bold]")
    console.print(f"4x end   : {rem4:>5} left ({p4:.1f}%)")
    console.print(f"2x end   : {rem2:>5} left ({p2:.1f}%)")
    console.print(f"OVERLOAD : {rem1:>5} left ({p1:.1f}%)")

    console.print("\n[bold]Games[/bold]")
    console.print(f"Played DM      : {dm_played:.1f}")
    console.print(f"Played Comp    : {comp_played:.1f}")
    console.print(f"To Overload DM : {dm_need:.1f}")
    console.print(f"To Overload CP : {comp_need:.1f}")

    console.print("\n[bold]Time[/bold]")
    console.print(f"Spent (DM)  : {dm_played*DM_TIME:.0f} min")
    console.print(f"Needed (DM) : {dm_need*DM_TIME:.0f} min")

    console.print("\n[bold]Rank[/bold]")
    console.print(f"XP to next rank: {xp_to_rank}")

# ─────────────────────────────
# UPDATE / DELETE / TABLE same style
# ─────────────────────────────

@app.command()
def update():
    data = load()
    w = week_now()
    data = ensure_week_exists(data, w)
    row = data[str(w)]

    medal = typer.prompt("Medal", default=row["medal"])
    rank = typer.prompt("Rank", default=row["rank"])
    xp = typer.prompt("XP", default=row["xp"])
    mission = typer.prompt("Mission XP", default=row["mission_actual"])

    abs_xp = to_abs(medal, rank, xp)
    prev_abs = data.get(str(w - 1), {}).get("abs_xp", abs_xp)

    gained_total = max(0, abs_xp - prev_abs - mission)
    basic = reverse_basic_from_total(gained_total)

    _, reduced, _ = compute_xp(basic)

    row.update({
        "abs_xp": abs_xp,
        "rank": rank,
        "xp": xp,
        "medal": medal,
        "basic_xp": int(basic),
        "reduced_xp": int(reduced),
        "mission_actual": mission
    })

    save(data)
    print("[green]Updated[/green]")

@app.command()
def delete():
    data = load()
    week = typer.prompt("Week")

    if week not in data:
        print("[red]Not found[/red]")
        return

    if typer.confirm(f"Delete week {week}?"):
        del data[week]
        save(data)
        print("[yellow]Deleted[/yellow]")

@app.command()
def table():
    data = load()

    table = Table(title="CS2 XP Data")

    cols = [
        "week","abs_xp","rank","xp","medal",
        "basic_xp","reduced_xp",
        "mission_actual","mission_max",
        "date_start","date_end"
    ]

    for c in cols:
        table.add_column(c)

    for w in sorted(data.keys(), key=int):
        r = data[w]
        table.add_row(*(str(r[c]) if c != "week" else w for c in cols))

    console.print(table)

# ─────────────────────────────
# INTERACTIVE
# ─────────────────────────────

def interactive():
    console.print(Panel.fit(
        "[bold cyan]🎯 CS2 XP Tracker[/bold cyan]\n\n"
        "status | update | delete | table | exit"
    ))

    while True:
        try:
            cmd = pt_prompt("[cs2xp] > ").strip() if USE_PROMPT_TOOLKIT else input("[cs2xp] > ").strip()

            if cmd in ("exit","quit"):
                break

            if cmd == "help":
                print("status, update, delete, table, exit")
                continue

            try:
                app(args=cmd.split(), standalone_mode=False)
            except SystemExit:
                pass

        except Exception as e:
            print(f"[red]{e}[/red]")

if __name__ == "__main__":
    interactive()
