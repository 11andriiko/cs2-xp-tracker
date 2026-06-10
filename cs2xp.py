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

    # mission
    m_cur = row["mission_actual"]
    m_max = row["mission_max"]
    m_pct = (m_cur / m_max * 100) if m_max else 0

    # approximations
    dm_played = basic / DM_XP
    comp_played = basic / COMP_XP

    dm_need = rem1 / DM_XP
    comp_need = rem1 / COMP_XP

    # time
    dm_time_spent = dm_played * DM_TIME
    dm_time_need = dm_need * DM_TIME
    comp_time_spent = comp_played * COMP_TIME
    comp_time_need = comp_need * COMP_TIME

    # rank
    xp_to_rank = XP_PER_RANK - row["xp"]

    # ───────── OVERLOAD PROJECTION ─────────
    xp_now_total, _, _ = compute_xp(basic)
    xp_after_total, _, _ = compute_xp(basic + rem1)

    gained_to_overload = xp_after_total - xp_now_total
    future_abs = row["abs_xp"] + gained_to_overload

    future_medal = future_abs // XP_PER_MEDAL
    rem_after_medal = future_abs % XP_PER_MEDAL

    future_rank = rem_after_medal // XP_PER_RANK + 1
    future_xp = rem_after_medal % XP_PER_RANK

    # ───────── PRINT ─────────

    console.print(Panel.fit(f"[bold cyan]Week {w}[/bold cyan]"))
    
    console.print("\n[bold]Current XP Status[/bold]")
    console.print(f"Medal: {row['medal']} | Rank: {row['rank']} | XP: {row['xp']}")
    console.print("[bold]At XP Overload[/bold]")
    console.print(f"Medal: {future_medal} | Rank: {future_rank} | XP: {future_xp}")

    console.print(f"\n[bold green]Current Stage:[/bold green] {stage}")
    # ───────── 4x ─────────
    earned4_basic = min(basic, BASIC_4X)
    earned4_xp = earned4_basic * 4
    if stage == "4x":
        left_basic = BASIC_4X - basic
        left_xp = left_basic * 4
        pct = (basic / BASIC_4X) * 100
        console.print(
            f"4x : Earned: {int(earned4_xp)} XP ({int(earned4_basic)} Basic XP) | "
            f"Left: {int(left_xp)} XP ({int(left_basic)} Basic XP)"
        )
    else:
        console.print(
            f"[dim]4x : Earned: {int(earned4_xp)} XP ({int(earned4_basic)} Basic XP)[/dim]"
        )

    # ───────── 2x ─────────
    earned2_basic = max(0, min(basic - BASIC_4X, BASIC_2X))
    earned2_xp = earned2_basic * 2
    if stage == "2x":
        left_basic = BASIC_2X - earned2_basic
        left_xp = left_basic * 2
        pct = (earned2_basic / BASIC_2X) * 100
        console.print(
            f"2x : Earned: {int(earned2_xp)} XP ({int(earned2_basic)} Basic XP) | "
            f"Left: {int(left_xp)} XP ({int(left_basic)} Basic XP)"
        )
    elif basic <= BASIC_4X:
        console.print(
            f"[dim]2x : Left: {BASIC_2X * 2} XP ({BASIC_2X} Basic XP)[/dim]"
        )
    else:
        console.print(
            f"[dim]2x : Earned: {int(earned2_xp)} XP ({int(earned2_basic)} Basic XP)[/dim]"
        )

    # ───────── 1x ─────────
    earned1_basic = max(0, min(basic - BASIC_4X - BASIC_2X, BASIC_1X))
    if stage == "1x":
        left_basic = BASIC_1X - earned1_basic
        pct = (earned1_basic / BASIC_1X) * 100
        console.print(
            f"1x : Earned: {int(earned1_basic)} XP ({int(earned1_basic)} Basic XP) | "
            f"Left: {int(left_basic)} Basic XP"
        )
    elif basic <= BASIC_4X + BASIC_2X:
        console.print(
            f"[dim]1x : Left: {BASIC_1X} Basic XP[/dim]"
        )
    else:
        console.print(
            f"[dim]1x : Earned: {int(earned1_basic)} XP ({int(earned1_basic)} Basic XP)[/dim]"
        )

    # ───────── 0.175x ─────────
    if stage == "0.175x":
        extra_basic = basic - BASIC_CAP
        _, reduced_xp, _ = compute_xp(basic)
        console.print(
            f"0.175x : Earned: {int(reduced_xp)} XP (~{int(extra_basic)} Basic XP)"
        )

    console.print("\n[bold]Progress[/bold]")
    # basic progress within stage and total
    stage_cap = {
        "4x": BASIC_4X,
        "2x": BASIC_2X,
        "1x": BASIC_1X,
        "0.175x": BASIC_CAP
    }[stage]
    if stage == "4x":
        stage_cur = basic
    elif stage == "2x":
        stage_cur = basic - BASIC_4X
    elif stage == "1x":
        stage_cur = basic - BASIC_4X - BASIC_2X
    else:
        stage_cur = basic
    console.print(
        f"Stage XP   : {int(stage_cur)}/{int(stage_cap)} "
        f"({(stage_cur/stage_cap)*100:.1f}%) {bar(stage_cur, stage_cap)}"
    )
    console.print(
        f"Total XP   : {basic:.0f}/{t1} ({(basic/t1)*100:.1f}%) {bar(basic, t1)}"
    )
    console.print(
        f"Mission XP : {m_cur}/{m_max} ({m_pct:.1f}%) {bar(m_cur, m_max)}"
    )

    console.print("\n[bold]Playtime Estimation[/bold]")
    console.print(
        f"DM   : Played: {dm_played:.1f} (~{dm_time_spent:.1f} min or ~{dm_time_spent/60:.1f} hr)  |  "
        f"Left: {dm_need:.1f} (~{dm_time_need:.1f} min or ~{dm_time_need/60:.1f} hr)"
    )
    console.print(
        f"Comp : Played: {comp_played:.1f} (~{comp_time_spent:.1f} min or ~{comp_time_spent/60:.1f} hr)  |  "
        f"Left: {comp_need:.1f} (~{comp_time_need:.1f} min or ~{comp_time_need/60:.1f} hr)"
    )

    # ───────── TARGET: RANK-UP / WEEKLY DROP ─────────

    # detect weekly drop
    is_weekly = (row["rank"] == prev["rank"] and row["medal"] == prev["medal"])
    console.print("\n[bold]To Weekly Drop[/bold]" if is_weekly else "\n[bold]To Rank-Up[/bold]")
    xp_needed = XP_PER_RANK - row["xp"]

    # simulate earning XP
    sim_basic = basic
    sim_xp = 0

    while sim_xp < xp_needed:
        gained, _, sim_stage = compute_xp(sim_basic + 1)
        gained_prev, _, _ = compute_xp(sim_basic)
        delta = gained - gained_prev
        sim_xp += delta
        sim_basic += 1

    # mission impact
    mission_left = max(0, m_max - m_cur)
    # ───────── OUTPUT ─────────

    basic_needed_no_mission = sim_basic - basic

    # playtime (no mission)
    dm_needed_nm = basic_needed_no_mission / DM_XP
    comp_needed_nm = basic_needed_no_mission / COMP_XP
    dm_time_nm = dm_needed_nm * DM_TIME
    comp_time_nm = comp_needed_nm * COMP_TIME
    console.print(
        f"XP needed  : {xp_needed} XP (~{int(basic_needed_no_mission)} Basic XP)"
    )
    console.print(
        f"Stage Flow : {stage} → {sim_stage}"
    )

    # ───────── WITH / WITHOUT MISSION ─────────
    if mission_left > 0:
        xp_after_mission = max(0, xp_needed - mission_left)
        # simulate AGAIN but with mission reducing needed XP
        sim_basic_m = basic
        sim_xp_m = 0
        while sim_xp_m < xp_after_mission:
            gained, _, _ = compute_xp(sim_basic_m + 1)
            gained_prev, _, _ = compute_xp(sim_basic_m)
            sim_xp_m += (gained - gained_prev)
            sim_basic_m += 1

        basic_needed_with_mission = sim_basic_m - basic
        # playtime (with mission)
        dm_needed_m = basic_needed_with_mission / DM_XP
        comp_needed_m = basic_needed_with_mission / COMP_XP
        dm_time_m = dm_needed_m * DM_TIME
        comp_time_m = comp_needed_m * COMP_TIME

        console.print(
            f"Left without mission : ~{int(basic_needed_no_mission)} Basic XP | "
            f"DM {dm_needed_nm:.1f} (~{dm_time_nm:.0f} min or ~{dm_time_nm/60:.1f} hr)  |  "
            f"Comp {comp_needed_nm:.1f} (~{comp_time_nm:.0f} min or ~{comp_time_nm/60:.1f} hr)"
        )
        console.print(
            f"Left with mission    : ~{int(basic_needed_with_mission)} Basic XP | "
            f"DM {dm_needed_m:.1f} (~{dm_time_m:.0f} min or ~{dm_time_m/60:.1f} hr)  |  "
            f"Comp {comp_needed_m:.1f} (~{comp_time_m:.0f} min or ~{comp_time_m/60:.1f} hr)"
        )
    else:
        console.print(
            f"Left       : ~{int(basic_needed_no_mission)} Basic XP | "
            f"DM {dm_needed_nm:.1f} (~{dm_time_nm:.0f} min or ~{dm_time_nm/60:.1f} hr)  |  "
            f"Comp {comp_needed_nm:.1f} (~{comp_time_nm:.0f} min or ~{comp_time_nm/60:.1f} hr)"
        )

# ─────────────────────────────
# UPDATE / DELETE / TABLE
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
