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
# STATUS LOGIC (shared)
# ─────────────────────────────

def run_status():
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

    # remaining to 1x cap
    rem1 = max(0, t1 - basic)

    # mission
    m_cur = row["mission_actual"]
    m_max = row["mission_max"]
    m_pct = (m_cur / m_max * 100) if m_max else 0

    # approximations
    dm_played   = basic / DM_XP
    comp_played = basic / COMP_XP
    dm_need     = rem1 / DM_XP
    comp_need   = rem1 / COMP_XP

    # time
    dm_time_spent  = dm_played   * DM_TIME
    dm_time_need   = dm_need     * DM_TIME
    comp_time_spent = comp_played * COMP_TIME
    comp_time_need  = comp_need   * COMP_TIME

    # ───────── OVERLOAD PROJECTION ─────────
    xp_now_total,   _, _ = compute_xp(basic)
    xp_after_total, _, _ = compute_xp(basic + rem1)

    gained_to_overload = xp_after_total - xp_now_total
    future_abs = row["abs_xp"] + gained_to_overload

    future_medal      = future_abs // XP_PER_MEDAL
    rem_after_medal   = future_abs % XP_PER_MEDAL
    future_rank       = rem_after_medal // XP_PER_RANK + 1
    future_xp         = rem_after_medal % XP_PER_RANK

    # ───────── PRINT ─────────

    console.print(Panel.fit(f"[bold cyan]Week {w}[/bold cyan]"))

    console.print("\n[bold]Current XP Status[/bold]")
    console.print(f"Medal: {row['medal']} | Rank: {row['rank']} | XP: {row['xp']}")
    console.print("[bold]At XP Overload[/bold]")
    console.print(f"Medal: {future_medal} | Rank: {future_rank} | XP: {future_xp}")

    # ───────── XP Progress (aligned) ─────────
    console.print("\n[bold]XP Progress[/bold]")

    if stage == "4x":
        stage_cur = basic
        stage_cap = BASIC_4X
    elif stage == "2x":
        stage_cur = basic - BASIC_4X
        stage_cap = BASIC_2X
    elif stage == "1x":
        stage_cur = basic - BASIC_4X - BASIC_2X
        stage_cap = BASIC_1X
    else:
        stage_cur = basic
        stage_cap = BASIC_CAP

    # Build the numeric parts first so we can measure their width
    stage_nums   = f"{int(stage_cur)}/{int(stage_cap)}"
    total_nums   = f"{int(basic)}/{t1}"
    mission_nums = f"{m_cur}/{m_max}"

    stage_pct   = f"({(stage_cur / stage_cap) * 100:.1f}%)" if stage_cap else "(0.0%)"
    total_pct   = f"({(basic / t1) * 100:.1f}%)"
    mission_pct = f"({m_pct:.1f}%)"

    # fixed widths for alignment
    W_NUMS = max(len(stage_nums), len(total_nums), len(mission_nums))
    W_PCT  = max(len(stage_pct),  len(total_pct),  len(mission_pct))

    console.print(
        f"Stage XP   : {stage_nums:<{W_NUMS}} {stage_pct:<{W_PCT}} {bar(stage_cur, stage_cap)}"
    )
    console.print(
        f"Total XP   : {total_nums:<{W_NUMS}} {total_pct:<{W_PCT}} {bar(basic, t1)}"
    )
    console.print(
        f"Mission XP : {mission_nums:<{W_NUMS}} {mission_pct:<{W_PCT}} {bar(m_cur, m_max)}"
    )

    console.print(f"\n[bold green]Current Stage:[/bold green] {stage}")

    # ───────── 4x ─────────
    earned4_basic = min(basic, BASIC_4X)
    earned4_xp    = earned4_basic * 4
    if stage == "4x":
        left_basic = BASIC_4X - basic
        left_xp    = left_basic * 4
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
    earned2_xp    = earned2_basic * 2
    if stage == "2x":
        left_basic = BASIC_2X - earned2_basic
        left_xp    = left_basic * 2
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
        console.print(
            f"1x : Earned: {int(earned1_basic)} XP ({int(earned1_basic)} Basic XP) | "
            f"Left: {int(left_basic)} Basic XP"
        )
    elif basic <= BASIC_4X + BASIC_2X:
        console.print(f"[dim]1x : Left: {BASIC_1X} Basic XP[/dim]")
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

    # ───────── Playtime ─────────
    console.print("\n[bold]Playtime Estimation[/bold]")

    # Collect the four raw float triples: (games, minutes, hours)
    _pt = [
        (dm_played,   dm_time_spent,   dm_time_spent   / 60),
        (dm_need,     dm_time_need,    dm_time_need    / 60),
        (comp_played, comp_time_spent, comp_time_spent / 60),
        (comp_need,   comp_time_need,  comp_time_need  / 60),
    ]

    # Pre-render each float with its format so we can measure widths
    _games_s = [f"{g:.1f}"  for g, _m, _h in _pt]
    _min_s   = [f"{m:.1f}"  for _g, m, _h in _pt]
    _hr_s    = [f"{h:.1f}"  for _g, _m, h in _pt]

    W_G = max(len(s) for s in _games_s)
    W_M = max(len(s) for s in _min_s)
    W_H = max(len(s) for s in _hr_s)

    def pt_cell(i):
        return (f"{_games_s[i]:>{W_G}} "
                f"(~{_min_s[i]:>{W_M}} min or "
                f"~{_hr_s[i]:>{W_H}} hr)")

    console.print(f"DM   : Played: {pt_cell(0)}  |  Left: {pt_cell(1)}")
    console.print(f"Comp : Played: {pt_cell(2)}  |  Left: {pt_cell(3)}")

    # ───────── TARGET: RANK-UP / WEEKLY DROP ─────────
    is_weekly = (row["rank"] == prev["rank"] and row["medal"] == prev["medal"])
    console.print("\n[bold]To Weekly Drop[/bold]" if is_weekly else "\n[bold]To Rank-Up[/bold]")
    xp_needed = XP_PER_RANK - row["xp"]

    sim_basic = basic
    sim_xp    = 0
    while sim_xp < xp_needed:
        gained,      _, sim_stage = compute_xp(sim_basic + 1)
        gained_prev, _, _         = compute_xp(sim_basic)
        sim_xp    += gained - gained_prev
        sim_basic += 1

    mission_left             = max(0, m_max - m_cur)
    basic_needed_no_mission  = sim_basic - basic
    dm_needed_nm             = basic_needed_no_mission / DM_XP
    comp_needed_nm           = basic_needed_no_mission / COMP_XP
    dm_time_nm               = dm_needed_nm   * DM_TIME
    comp_time_nm             = comp_needed_nm * COMP_TIME

    console.print(f"XP needed  : {xp_needed} XP (~{int(basic_needed_no_mission)} Basic XP)")
    console.print(f"Stage Flow : {stage} → {sim_stage}")

    if mission_left > 0:
        xp_after_mission = max(0, xp_needed - mission_left)
        sim_basic_m = basic
        sim_xp_m    = 0
        while sim_xp_m < xp_after_mission:
            gained,      _, _ = compute_xp(sim_basic_m + 1)
            gained_prev, _, _ = compute_xp(sim_basic_m)
            sim_xp_m    += gained - gained_prev
            sim_basic_m += 1

        basic_needed_with_mission = sim_basic_m - basic
        dm_needed_m   = basic_needed_with_mission / DM_XP
        comp_needed_m = basic_needed_with_mission / COMP_XP
        dm_time_m     = dm_needed_m   * DM_TIME
        comp_time_m   = comp_needed_m * COMP_TIME

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
# UPDATE LOGIC (shared)
# ─────────────────────────────

def run_update(mode="full"):
    """
    mode: "full"    → ask medal, rank, xp, mission
          "medal"   → ask medal, rank, xp  (no mission)
          "rank"    → ask rank, xp         (medal stays, no mission)
          "xp"      → ask xp only          (rank & medal stay, no mission)
          "mission" → ask mission XP only
    """
    data = load()
    w    = week_now()
    data = ensure_week_exists(data, w)
    row  = data[str(w)]

    # snapshot of values before any changes
    old_medal   = row["medal"]
    old_rank    = row["rank"]
    old_xp      = row["xp"]
    old_mission = row["mission_actual"]

    new_medal   = old_medal
    new_rank    = old_rank
    new_xp      = old_xp
    new_mission = old_mission

    # ── FULL (default, no arg) ──
    if mode == "full":
        raw       = input(f"Medal [{old_medal}]: ").strip()
        new_medal = int(raw) if raw else old_medal

        raw      = input(f"Rank [{old_rank}]: ").strip()
        new_rank = int(raw) if raw else old_rank

        raw     = input(f"XP [{old_xp}]: ").strip()
        new_xp  = int(raw) if raw else old_xp

        raw         = input(f"Mission XP [{old_mission}]: ").strip()
        new_mission = int(raw) if raw else old_mission

    # ── MEDAL level ──
    elif mode == "medal":
        raw       = input(f"Medal [{old_medal}]: ").strip()
        new_medal = int(raw) if raw else old_medal

        if new_medal < old_medal:
            console.print(
                f"[yellow]⚠  Medal {new_medal} is lower than current {old_medal}.[/yellow]\n"
                f"[yellow]   Are you sure? (yes/no)[/yellow]"
            )
            if input("> ").strip().lower() not in ("yes", "y"):
                console.print("[red]Update cancelled.[/red]")
                return

        raw      = input(f"Rank [{old_rank}]: ").strip()
        new_rank = int(raw) if raw else old_rank

        raw    = input(f"XP [{old_xp}]: ").strip()
        new_xp = int(raw) if raw else old_xp

    # ── RANK level ──
    elif mode == "rank":
        raw      = input(f"Rank [{old_rank}]: ").strip()
        new_rank = int(raw) if raw else old_rank

        if new_rank < old_rank:
            console.print(
                f"[yellow]⚠  Rank {new_rank} is lower than current {old_rank}.[/yellow]\n"
                f"[yellow]   Are you sure? (yes/no)[/yellow]"
            )
            if input("> ").strip().lower() not in ("yes", "y"):
                console.print("[red]Update cancelled.[/red]")
                return

        raw    = input(f"XP [{old_xp}]: ").strip()
        new_xp = int(raw) if raw else old_xp

    # ── XP level ──
    elif mode == "xp":
        raw    = input(f"XP [{old_xp}]: ").strip()
        new_xp = int(raw) if raw else old_xp

        if new_xp < old_xp:
            console.print(
                f"[yellow]⚠  XP {new_xp} is lower than current {old_xp}.[/yellow]\n"
                f"[yellow]   Did you mean to update rank as well? Try 'u -rank'.[/yellow]\n"
                f"[yellow]   Continue anyway? (yes/no)[/yellow]"
            )
            if input("> ").strip().lower() not in ("yes", "y"):
                console.print("[red]Update cancelled.[/red]")
                return

    # ── MISSION only ──
    elif mode == "mission":
        raw         = input(f"Mission XP [{old_mission}]: ").strip()
        new_mission = int(raw) if raw else old_mission

        if new_mission < old_mission:
            console.print(
                f"[yellow]⚠  Mission XP {new_mission} is lower than current {old_mission}.[/yellow]\n"
                f"[yellow]   Continue anyway? (yes/no)[/yellow]"
            )
            if input("> ").strip().lower() not in ("yes", "y"):
                console.print("[red]Update cancelled.[/red]")
                return

    # ── Nothing changed? ──
    if (new_medal == old_medal and new_rank == old_rank
            and new_xp == old_xp and new_mission == old_mission):
        console.print("[dim]No changes made.[/dim]")
        return

    # ── Compute and save ──
    abs_xp   = to_abs(new_medal, new_rank, new_xp)
    prev_abs = data.get(str(w - 1), {}).get("abs_xp", abs_xp)

    gained_total = max(0, abs_xp - prev_abs - new_mission)
    basic        = reverse_basic_from_total(gained_total)
    _, reduced, _ = compute_xp(basic)

    row.update({
        "abs_xp":         abs_xp,
        "rank":           new_rank,
        "xp":             new_xp,
        "medal":          new_medal,
        "basic_xp":       int(basic),
        "reduced_xp":     int(reduced),
        "mission_actual": new_mission
    })

    save(data)
    console.print(
        f"[green]✓ Saved:[/green] "
        f"Medal: {new_medal} | Rank: {new_rank} | XP: {new_xp} | Mission: {new_mission}"
    )

# ─────────────────────────────
# DELETE / TABLE LOGIC (shared)
# ─────────────────────────────

def run_delete():
    data = load()
    week = input("Week to delete: ").strip()

    if week not in data:
        console.print("[red]Not found[/red]")
        return

    confirm = input(f"Delete week {week}? (yes/no): ").strip().lower()
    if confirm in ("yes", "y"):
        del data[week]
        save(data)
        console.print("[yellow]Deleted[/yellow]")
    else:
        console.print("[dim]Cancelled.[/dim]")

def run_table():
    data = load()

    t = Table(title="CS2 XP Data")

    cols = [
        "week", "abs_xp", "rank", "xp", "medal",
        "basic_xp", "reduced_xp",
        "mission_actual", "mission_max",
        "date_start", "date_end"
    ]

    for c in cols:
        t.add_column(c)

    for w in sorted(data.keys(), key=int):
        r = data[w]
        t.add_row(*(str(r[c]) if c != "week" else w for c in cols))

    console.print(t)

# ─────────────────────────────
# HELP
# ─────────────────────────────

HELP_TEXT = """
[bold cyan]CS2 XP Tracker — Help[/bold cyan]

[bold]Commands[/bold]

  [cyan]status[/cyan]  /  [cyan]s[/cyan]  /  [cyan]stat[/cyan]
      Show current week's XP progress, stage breakdown,
      playtime estimates, and rank-up / weekly drop targets.

  [cyan]update[/cyan]  /  [cyan]u[/cyan]  /  [cyan]upd[/cyan]  [-medal | -rank | -xp | -mission]
      Update this week's data.  Default (no argument) asks for
      medal → rank → xp → mission in order.

      Arguments let you enter only what changed:
        [cyan]u -medal[/cyan] / [cyan]-med[/cyan]   update medal, rank, xp
        [cyan]u -rank[/cyan] / [cyan]-r[/cyan]      update rank, xp
        [cyan]u -xp[/cyan]             update xp only
        [cyan]u -mission[/cyan] / [cyan]-mis[/cyan] update mission XP only

  [cyan]delete[/cyan]  /  [cyan]d[/cyan]  /  [cyan]del[/cyan]
      Delete a week's data by number.

  [cyan]table[/cyan]  /  [cyan]t[/cyan]
      Display all stored weeks in a table.

  [cyan]help[/cyan]  /  [cyan]h[/cyan]
      Show this help message.

  [cyan]exit[/cyan]  /  [cyan]quit[/cyan]  /  [cyan]stop[/cyan]  /  [cyan]e[/cyan]  /  [cyan]q[/cyan]
      Exit the tracker.

[bold]Notes[/bold]
  • Commands are case-insensitive: [cyan]S[/cyan], [cyan]STATUS[/cyan], [cyan]status[/cyan] all work.
  • Square brackets in prompts show the current stored value.
    Press Enter to keep it unchanged.
"""

def run_help():
    console.print(Panel(HELP_TEXT.strip(), expand=False))

# ─────────────────────────────
# INTERACTIVE
# ─────────────────────────────

COMMAND_MAP = {
    # status
    "status": ("status", None),
    "s":      ("status", None),
    "stat":   ("status", None),
    # update
    "update": ("update", "full"),
    "u":      ("update", "full"),
    "upd":    ("update", "full"),
    # delete
    "delete": ("delete", None),
    "d":      ("delete", None),
    "del":    ("delete", None),
    # table
    "table":  ("table",  None),
    "t":      ("table",  None),
    # help
    "help":   ("help",   None),
    "h":      ("help",   None),
    # exit
    "exit":   ("exit",   None),
    "quit":   ("exit",   None),
    "stop":   ("exit",   None),
    "e":      ("exit",   None),
    "q":      ("exit",   None),
}

# Valid arguments per canonical command → {arg_string: mode}
COMMAND_ARGS = {
    "update": {
        "-medal":   "medal",
        "-med":     "medal",
        "-rank":    "rank",
        "-r":       "rank",
        "-xp":      "xp",
        "-mission": "mission",
        "-mis":     "mission",
    },
    "status": {},
    "delete": {},
    "table":  {},
    "help":   {},
    "exit":   {},
}

# Map every alias to its canonical command name
_VERB_TO_CMD = {alias: cmd for alias, (cmd, _) in COMMAND_MAP.items()}

def parse_command(raw: str):
    """
    Returns (command, mode, error_msg) where error_msg is None on success.
    Handles: "status", "s", "u -xp", "UPDATE -RANK", "u -bad", "s -bad",
             "u -xp -medal" (too many args) etc.
    """
    parts = raw.strip().lower().split()
    if not parts:
        return None, None, None

    verb = parts[0]
    args = parts[1:]   # everything after the verb

    # unknown verb
    cmd = _VERB_TO_CMD.get(verb)
    if cmd is None:
        return None, None, f"[red]Unknown command: '{raw}'. Type 'help' or 'h' for usage.[/red]"

    valid_args = COMMAND_ARGS.get(cmd, {})

    # no argument → default mode
    if not args:
        default_mode = "full" if cmd == "update" else None
        return cmd, default_mode, None

    # more than one argument → always an error
    if len(args) > 1:
        return None, None, (
            f"[red]Too many arguments for '{verb}' (only one argument allowed).[/red]"
        )

    arg = args[0]

    # argument given but this command accepts none
    if not valid_args:
        return None, None, (
            f"[red]Command '{verb}' does not accept arguments (got '{arg}').[/red]"
        )

    # valid argument
    if arg in valid_args:
        return cmd, valid_args[arg], None

    # unrecognised argument
    valid_list = "  ".join(k for k in valid_args)
    return None, None, (
        f"[red]Unknown argument '{arg}' for '{verb}'.[/red]\n"
        f"[red]Valid arguments: {valid_list}[/red]"
    )


def interactive():
    console.print(Panel.fit(
        "[bold cyan]🎯 CS2 XP Tracker[/bold cyan]\n\n"
        "Track your weekly XP progress in CS2.\n\n"
        "Quick start:\n"
        "  [cyan]status[/cyan]  – see current week's progress\n"
        "  [cyan]update[/cyan]  – enter your latest XP\n"
        "  [cyan]help[/cyan]    – show all commands\n"
        "  [cyan]exit[/cyan]    – quit\n\n"
        "[dim]Commands have single-letter shortcuts: s / u / d / t / h / e[/dim]"
    ))

    while True:
        try:
            raw = (
                pt_prompt("[cs2xp] > ").strip()
                if USE_PROMPT_TOOLKIT
                else input("[cs2xp] > ").strip()
            )

            if not raw:
                continue

            cmd, mode, err = parse_command(raw)

            if err is not None:
                console.print(err)
                continue

            if cmd is None:
                continue

            if cmd == "exit":
                console.print("[dim]Session closed.[/dim]")
                break

            if cmd == "status":
                run_status()
            elif cmd == "update":
                run_update(mode or "full")
            elif cmd == "delete":
                run_delete()
            elif cmd == "table":
                run_table()
            elif cmd == "help":
                run_help()

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session closed.[/dim]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    interactive()
