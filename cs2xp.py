import json
import sys

IS_FROZEN = getattr(sys, 'frozen', False)
import datetime
from pathlib import Path
from rich.table import Table
from rich.panel import Panel
from rich.console import Console

try:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import InMemoryHistory
    _PT_HISTORY = InMemoryHistory()
    USE_PROMPT_TOOLKIT = True
except ImportError:
    USE_PROMPT_TOOLKIT = False
    _PT_HISTORY = None

console = Console()

# ═══════════════════════════════════════════
# APP / VERSION / PATHS
# ═══════════════════════════════════════════

APP_NAME    = "CS2 XP Tracker"
__version__ = "1.0.0"

GITHUB_OWNER = "11andriiko"
GITHUB_REPO  = "cs2-xp-tracker"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

def app_dir() -> Path:
    """Folder the running program lives in (.exe folder when frozen, script folder otherwise)."""
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

DATA_FILE = app_dir() / "cs2xp_data.json"

# ═══════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════

XP_PER_RANK  = 5000
RANKS_MEDAL  = 39
XP_PER_MEDAL = XP_PER_RANK * RANKS_MEDAL

# Each entry: (basic_xp_cap_for_stage | None, multiplier, xp_limit_for_stage | None, label)
#
# xp_limit is the maximum bonus-inclusive XP this stage can ever output. It is
# normally basic_xp_cap * multiplier, but at the 4x stage it is NOT exactly
# that: the stage has a fixed bonus-XP pool, and the last basic-XP point
# earned in the stage only gets whatever's left in that pool rather than a
# full extra (multiplier-1) share. Concretely, stage 4x has a basic cap of
# 1167 but a hard xp_limit of 4667 (not 1167*4=4668) — the 1167th basic XP
# only contributes the 2 leftover bonus XP instead of a full 3, and the 1
# remaining bonus XP that the pool can't cover is simply never awarded.
# Last stage has no cap/limit — continues indefinitely.
XP_STAGES = [
    (1167, 4,     4667, "4x"),
    (1500, 2,     3000, "2x"),
    (3500, 1,     3500, "1x"),
    (None, 0.175, None, "0.175x"),
]

# Derived cumulative thresholds
BASIC_4X     = XP_STAGES[0][0]                     # 1167
BASIC_2X     = XP_STAGES[1][0]                     # 1500
BASIC_1X     = XP_STAGES[2][0]                     # 3500
BASIC_CAP    = BASIC_4X + BASIC_2X + BASIC_1X      # 6167
REDUCED_MULT = XP_STAGES[3][1]                     # 0.175

REDUCED_XP_WARN = 1000

MISSION_CYCLE = [600, 1050, 1050, 550, 1050, 1050, 600, 1050]
FIRST_WED     = datetime.date(2026, 1, 7)
YEAR_END      = datetime.date(2026, 12, 31)

DM_XP     = 75
COMP_XP   = 390
DM_TIME   = 10
COMP_TIME = 30

# ═══════════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════════

def load():
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())

def save(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))

# ═══════════════════════════════════════════
# TIME HELPERS
# ═══════════════════════════════════════════

RESET_UTC_HOUR = 1        # weekly reset is Wednesday 01:00 UTC
LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=3))  # GMT+3

def week_now():
    # Shift UTC back by RESET_UTC_HOUR so the reset maps to 'midnight' for date arithmetic
    shifted = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=RESET_UTC_HOUR)
    return max(1, (shifted.date() - FIRST_WED).days // 7 + 1)

def get_week_dates(week):
    start = FIRST_WED + datetime.timedelta(days=(week - 1) * 7)
    return start, min(start + datetime.timedelta(days=6), YEAR_END)

def get_week_dates_iso(week):
    s, e = get_week_dates(week)
    return s.isoformat(), e.isoformat()

def time_left_in_week(week):
    _, end = get_week_dates(week)
    # Reset fires on the Wednesday *after* end-date at RESET_UTC_HOUR UTC
    next_reset = datetime.datetime(end.year, end.month, end.day,
                                   tzinfo=datetime.timezone.utc) \
                 + datetime.timedelta(days=1, hours=RESET_UTC_HOUR)
    now = datetime.datetime.now(datetime.timezone.utc)
    return max(datetime.timedelta(0), next_reset - now)

def fmt_timedelta(td):
    s = int(td.total_seconds())
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m     = s // 60
    return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"

def mission_max(week):
    return MISSION_CYCLE[(week - 1) % 8]

def last_week_of_year():
    return max(1, (YEAR_END - FIRST_WED).days // 7 + 1)

def fmt_range(weeks):
    """Format a list of ints as compact range string: [3,4,5,6,7] → '3-7', [5] → '5'."""
    weeks = sorted(set(weeks))
    if not weeks:
        return ""
    if len(weeks) == 1:
        return str(weeks[0])
    # Check if it's a contiguous range
    if weeks == list(range(weeks[0], weeks[-1] + 1)):
        return f"{weeks[0]}-{weeks[-1]}"
    return ", ".join(str(w) for w in weeks)

def parse_week_range(raw):
    """'5' → [5],  '3-7' → [3,4,5,6,7],  else None."""
    raw = raw.strip()
    if "-" in raw:
        try:
            a, b = raw.split("-", 1)
            a, b = int(a), int(b)
            return list(range(a, b + 1)) if a <= b else None
        except ValueError:
            return None
    try:
        return [int(raw)]
    except ValueError:
        return None

# ═══════════════════════════════════════════
# XP MATH
# ═══════════════════════════════════════════

def to_abs(medal, rank, xp):
    return medal * XP_PER_MEDAL + (rank - 1) * XP_PER_RANK + xp

def abs_to_mrx(abs_xp):
    m   = abs_xp // XP_PER_MEDAL
    rem = abs_xp % XP_PER_MEDAL
    return m, rem // XP_PER_RANK + 1, rem % XP_PER_RANK

def compute_xp(basic):
    """Returns (total_xp_gained, reduced_xp, stage_label).

    Each capped stage has both a basic_xp cap and a hard xp_limit on the
    bonus-inclusive total it can output. Normally xp_limit == cap * mult,
    but the 4x stage's xp_limit is slightly below that (its bonus pool runs
    out one basic-XP-unit early), so the last basic XP point of that stage
    only yields whatever's left of the pool instead of a full extra share.
    """
    cum_basic, total = 0, 0
    for cap, mult, limit, label in XP_STAGES:
        if cap is None:
            extra = basic - cum_basic
            red   = extra * mult
            return total + red, red, label
        into = basic - cum_basic
        if into <= 0:
            return total, 0, label
        if into >= cap:
            # Whole stage consumed — output is the stage's fixed xp_limit
            # (this is what absorbs the 4x-stage rounding clip).
            total    += limit
            cum_basic += cap
            continue
        # Partial stage: standard multiply, clipped to the stage's pool
        # (clip only ever bites on the very last basic-XP unit of a stage).
        total += min(into * mult, limit)
        return total, 0, label
    return total, 0, XP_STAGES[-1][3]

def reverse_basic_from_total(total_xp):
    """Inverse of compute_xp. Assumes integer-ish basic XP inputs in practice
    (the app always works with integer basic XP), so the rare fractional
    ambiguity inside a stage's clipped final unit is a non-issue here."""
    cum_basic, rem = 0, total_xp
    for cap, mult, limit, label in XP_STAGES:
        if cap is None:
            return cum_basic + rem / mult
        if rem <= limit:
            lower_total = (cap - 1) * mult
            if rem <= lower_total:
                return cum_basic + rem / mult
            # Inside the clipped final basic-XP unit of this stage.
            frac = (rem - lower_total) / (limit - lower_total) if limit > lower_total else 1.0
            return cum_basic + (cap - 1) + frac
        rem -= limit
        cum_basic += cap
    return cum_basic

def stage_at_basic(basic):
    """Returns (label, basic_into_stage, stage_cap_or_None)."""
    cum = 0
    for cap, mult, limit, label in XP_STAGES:
        if cap is None or basic <= cum + cap:
            return label, basic - cum, cap
        cum += cap
    return XP_STAGES[-1][3], basic - BASIC_CAP, None

def stage_boundary_basic(basic):
    """Cumulative basic XP at end of current stage, or None if in final stage."""
    cum = 0
    for cap, mult, limit, label in XP_STAGES:
        boundary = cum + (cap or 0)
        if cap is None or basic <= boundary:
            return boundary if cap is not None else None
        cum += cap
    return None

def next_stage_label(current_label):
    for i, (_, _, _, lbl) in enumerate(XP_STAGES):
        if lbl == current_label and i + 1 < len(XP_STAGES):
            return XP_STAGES[i + 1][3]
    return None

def bar(cur, maxv, length=20):
    if not maxv:
        return ""
    f = int(min(cur / maxv, 1) * length)
    return "█" * f + "░" * (length - f)

# ═══════════════════════════════════════════
# WEEK DATA
# ═══════════════════════════════════════════

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
        rank, xp, medal = 1, 0, 0
    si, ei = get_week_dates_iso(week)
    data[w] = {
        "abs_xp": base_abs, "rank": rank, "xp": xp, "medal": medal,
        "basic_xp": 0, "reduced_xp": 0,
        "mission_actual": 0, "mission_max": mission_max(week),
        "date_start": si, "date_end": ei,
    }
    save(data)
    return data

def compute_row_fields(medal, rank, xp, mission, prev_abs):
    """Return dict of computed fields for a week given raw inputs."""
    abs_xp        = to_abs(medal, rank, xp)
    gained        = max(0, abs_xp - prev_abs - mission)
    basic         = reverse_basic_from_total(gained)
    _, reduced, _ = compute_xp(basic)
    return {
        "abs_xp":         abs_xp,
        "medal":          medal,
        "rank":           rank,
        "xp":             xp,
        "basic_xp":       int(basic),
        "reduced_xp":     int(reduced),
        "mission_actual": mission,
    }

# ═══════════════════════════════════════════
# TABLE / DISPLAY HELPERS
# ═══════════════════════════════════════════

TABLE_COLS = ["week", "abs_xp", "medal", "rank", "xp",
              "basic_xp", "reduced_xp", "mission_actual", "mission_max",
              "date_start", "date_end"]

def make_table(title):
    t = Table(title=title)
    for c in TABLE_COLS:
        t.add_column(c)
    return t

def build_table_row(week, row):
    return [str(week), str(row["abs_xp"]), str(row["medal"]), str(row["rank"]),
            str(row["xp"]), str(row["basic_xp"]), str(row["reduced_xp"]),
            str(row["mission_actual"]), str(row["mission_max"]),
            row.get("date_start", ""), row.get("date_end", "")]

def print_data_table(rows_dict, title, highlight=None):
    """Print a Rich table. `highlight` is a set of week ints to bold-cyan."""
    cur_w = week_now()
    hl    = highlight if highlight is not None else {cur_w}
    t     = make_table(title)
    for w in sorted(rows_dict, key=int):
        style = "bold cyan" if int(w) in hl else ""
        row   = build_table_row(int(w), rows_dict[w])
        t.add_row(*row, style=style) if style else t.add_row(*row)
    console.print(t)

def print_before_after(before, after, highlight):
    """Print a Before table then an After (preview) table."""
    def extract(src):
        return {w: src[w] for w in [str(x) for x in highlight] if w in src}
    print_data_table(extract(before), "Before",         highlight=set(highlight))
    print_data_table(extract(after),  "After (preview)", highlight=set(highlight))

def week_header(week):
    s, e   = get_week_dates(week)
    dates  = f"{s.strftime('%d %b')} – {e.strftime('%d %b %Y')}"
    base   = f"[bold cyan]Week {week}[/bold cyan]  [dim]{dates}[/dim]"
    if week == week_now():
        td  = time_left_in_week(week)
        base += f"  [yellow]⏱ {fmt_timedelta(td)} left[/yellow]"
    console.print(Panel.fit(base))

def print_mrx(label, medal, rank, xp, style=""):
    line = f"Medal: {medal} | Rank: {rank} | XP: {xp}"
    console.print(f"{label}[{style}]{line}[/{style}]" if style else f"{label}{line}")

def print_xp_status_block(row):
    basic   = row["basic_xp"]
    abs_now = row["abs_xp"]
    _, _, stage = compute_xp(basic)

    boundary = stage_boundary_basic(basic)
    if boundary is not None:
        t_boundary, _, _ = compute_xp(boundary)
        t_now,      _, _ = compute_xp(basic)
        sm, sr, sx = abs_to_mrx(int(abs_now + t_boundary - t_now))
        nxt        = next_stage_label(stage)
        stage_line = f"Medal: {sm} | Rank: {sr} | XP: {sx}  [dim](stage changes: {stage} → {nxt})[/dim]"
    else:
        stage_line = "(already in overload stage)"

    t_cap, _, _ = compute_xp(BASIC_CAP)
    t_now, _, _ = compute_xp(basic)
    om, or_, ox = abs_to_mrx(int(abs_now + t_cap - t_now))

    console.print("\n[bold]XP Status[/bold]")
    print_mrx("  Current : ", row["medal"], row["rank"], row["xp"])
    console.print(f"  Stage   : {stage_line}")
    print_mrx("  Overload: ", om, or_, ox)

# ═══════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════

def run_status(target_week=None):
    data = load()
    w    = target_week if target_week is not None else week_now()
    data = ensure_week_exists(data, w)

    row   = data[str(w)]
    prev  = data.get(str(w - 1), row)
    basic = row["basic_xp"]
    _, _, stage = compute_xp(basic)
    t1   = BASIC_CAP
    rem1 = max(0, t1 - basic)
    m_cur, m_max = row["mission_actual"], row["mission_max"]

    week_header(w)
    print_xp_status_block(row)

    # ── Progress bars ──
    lbl, into, scap = stage_at_basic(basic)
    total_now, _, _ = compute_xp(basic)
    total_cap, _, _ = compute_xp(BASIC_CAP)
    nums = [f"{int(into)}/{scap or '∞'}", f"{int(basic)}/{t1}", f"{int(total_now)}/{int(total_cap)}", f"{m_cur}/{m_max}"]
    pcts = [
        f"({into/scap*100:.1f}%)" if scap else "(overload)",
        f"({basic/t1*100:.1f}%)",
        f"({total_now/total_cap*100:.1f}%)" if total_cap else "(0.0%)",
        f"({m_cur/m_max*100:.1f}%)" if m_max else "(0.0%)",
    ]
    WN = max(len(s) for s in nums)
    WP = max(len(s) for s in pcts)

    console.print("\n[bold]XP Progress[/bold]")
    console.print(f"  Stage XP   : {nums[0]:<{WN}} {pcts[0]:<{WP}} {bar(into, scap or basic)}")
    console.print(f"  Basic XP   : {nums[1]:<{WN}} {pcts[1]:<{WP}} {bar(basic, t1)}")
    console.print(f"  Total XP   : {nums[2]:<{WN}} {pcts[2]:<{WP}} {bar(total_now, total_cap)}")
    console.print(f"  Mission XP : {nums[3]:<{WN}} {pcts[3]:<{WP}} {bar(m_cur, m_max)}")

    # ── Per-stage breakdown ──
    console.print(f"\n[bold green]Current Stage:[/bold green] {stage}")
    cum = 0
    for cap, mult, limit, label in XP_STAGES:
        if cap is None:
            if stage == label:
                extra = basic - BASIC_CAP
                _, red, _ = compute_xp(basic)
                console.print(f"  {label}: Earned: {int(red)} XP (~{int(extra)} Basic XP)")
            break
        earned_b = max(0, min(basic - cum, cap))
        earned_x = int(limit) if earned_b >= cap else int(min(earned_b * mult, limit))
        is_cur   = (stage == label)
        not_yet  = (basic <= cum)
        if is_cur:
            left_b, left_x = int(cap - earned_b), int(limit - earned_x)
            console.print(f"  {label}: Earned: {earned_x} XP ({int(earned_b)} Basic XP) | Left: {left_x} XP ({left_b} Basic XP)")
        elif not_yet:
            console.print(f"  [dim]{label}: Left: {int(limit)} XP ({cap} Basic XP)[/dim]")
        else:
            console.print(f"  [dim]{label}: Earned: {earned_x} XP ({int(earned_b)} Basic XP)[/dim]")
        cum += cap

    # ── Playtime ──
    def playtime_row(label, played_basic, need_basic):
        def cell(bx):
            games = bx / (DM_XP if "DM" in label else COMP_XP)
            mins  = games * (DM_TIME if "DM" in label else COMP_TIME)
            return games, mins, mins / 60
        return cell(played_basic), cell(need_basic)

    overloaded = (rem1 == 0)
    over_basic = max(0, basic - t1) if overloaded else 0
    right_basic = over_basic if overloaded else rem1

    dm_played_c,   dm_right_c   = playtime_row("DM",   basic, right_basic)
    comp_played_c, comp_right_c = playtime_row("Comp", basic, right_basic)
    all_cells = [dm_played_c, dm_right_c, comp_played_c, comp_right_c]

    gs = [f"{c[0]:.1f}" for c in all_cells]
    ms = [f"{c[1]:.1f}" for c in all_cells]
    hs = [f"{c[2]:.1f}" for c in all_cells]
    WG, WM, WH = max(len(s) for s in gs), max(len(s) for s in ms), max(len(s) for s in hs)

    def pt(i):
        return f"{gs[i]:>{WG}} (~{ms[i]:>{WM}} min or ~{hs[i]:>{WH}} hr)"

    right_label = "Over" if overloaded else "Left"
    console.print("\n[bold]Playtime Estimation[/bold]")
    console.print(f"  DM   : Played: {pt(0)}  |  {right_label}: {pt(1)}")
    console.print(f"  Comp : Played: {pt(2)}  |  {right_label}: {pt(3)}")

    # ── Rank-up / weekly drop ──
    is_weekly = (row["rank"] == prev["rank"] and row["medal"] == prev["medal"])
    xp_needed = XP_PER_RANK - row["xp"]
    console.print("\n[bold]To Weekly Drop[/bold]" if is_weekly else "\n[bold]To Rank-Up[/bold]")

    def simulate_basic_needed(xp_target):
        sb, sx = basic, 0
        _, _, s2 = compute_xp(sb)
        while sx < xp_target:
            g,  _, s2 = compute_xp(sb + 1)
            gp, _, _  = compute_xp(sb)
            sx += g - gp
            sb += 1
        return sb - basic, s2

    basic_nm, end_stage = simulate_basic_needed(xp_needed)
    mission_left = max(0, m_max - m_cur)

    def playtime_line(bx):
        dm, co = bx / DM_XP, bx / COMP_XP
        return f"DM {dm:.1f} (~{dm*DM_TIME:.0f} min or ~{dm*DM_TIME/60:.1f} hr)  |  Comp {co:.1f} (~{co*COMP_TIME:.0f} min or ~{co*COMP_TIME/60:.1f} hr)"

    console.print(f"  XP needed  : {xp_needed} XP (~{int(basic_nm)} Basic XP)")
    console.print(f"  Stage Flow : {stage} → {end_stage}")

    if mission_left > 0:
        basic_m, _ = simulate_basic_needed(max(0, xp_needed - mission_left))
        w_bx = max(len(str(int(basic_nm))), len(str(int(basic_m))))
        console.print(f"  Left without mission : ~{int(basic_nm):{w_bx}} Basic XP | {playtime_line(basic_nm)}")
        console.print(f"  Left with mission    : ~{int(basic_m):{w_bx}} Basic XP | {playtime_line(basic_m)}")
    else:
        console.print(f"  Left       : ~{int(basic_nm)} Basic XP | {playtime_line(basic_nm)}")

# ═══════════════════════════════════════════
# UPDATE
# ═══════════════════════════════════════════

def _ask(prompt, default):
    raw = input(f"{prompt} [{default}]: ").strip()
    return int(raw) if raw else default

def _confirm(prompt="Continue? (yes/no)"):
    return input(f"{prompt} ").strip().lower() in ("yes", "y")

# Defines which fields each mode asks for, and whether a decrease triggers a warning.
# Each entry: (field_key, prompt_label, warn_if_lower, warn_extra_msg)
_MODE_FIELDS = {
    "full":    [("medal",   "Medal",      True,  ""),
                ("rank",    "Rank",        False, ""),
                ("xp",      "XP",          False, ""),
                ("mission", "Mission XP",  False, "")],
    "medal":   [("medal",   "Medal",      True,  ""),
                ("rank",    "Rank",        False, ""),
                ("xp",      "XP",          False, "")],
    "rank":    [("rank",    "Rank",        True,  ""),
                ("xp",      "XP",          False, "")],
    "xp":      [("xp",      "XP",          True,  " Did you mean 'u -rank'?")],
    "mission": [("mission", "Mission XP",  True,  "")],
}

def run_update(mode="full"):
    data  = load()
    cur_w = week_now()

    w = _ask("Week", cur_w) if mode == "full" else cur_w
    data = ensure_week_exists(data, w)
    row  = data[str(w)]

    if w != cur_w:
        console.print(
            f"[yellow]⚠  Editing Week {w} (current: Week {cur_w}).[/yellow]\n"
            f"[yellow]   This will affect Week {w} and Week {w+1}'s derived values.[/yellow]"
        )

    old = {"medal": row["medal"], "rank": row["rank"],
           "xp":    row["xp"],    "mission": row["mission_actual"]}
    new = dict(old)

    # ── Collect inputs ──
    for field, label, warn_lower, extra in _MODE_FIELDS[mode]:
        val = _ask(label, old[field])
        if warn_lower and val < old[field]:
            console.print(f"[yellow]⚠  {label} {val} < current {old[field]}.{extra} Continue? (yes/no)[/yellow]")
            if not _confirm():
                console.print("[red]Update cancelled.[/red]"); return
        new[field] = val

    # ── Validate vs previous week ──
    prev_row = data.get(str(w - 1))
    if prev_row:
        new_abs = to_abs(new["medal"], new["rank"], new["xp"])
        if new_abs < prev_row["abs_xp"]:
            console.print(
                f"[red]✗  New abs XP ({new_abs}) < Week {w-1} abs XP "
                f"({prev_row['abs_xp']}). Update cancelled.[/red]"
            )
            return

    if new == old:
        console.print("[dim]No changes made.[/dim]"); return

    # ── Compute ──
    prev_abs   = data.get(str(w - 1), {}).get("abs_xp", to_abs(new["medal"], new["rank"], new["xp"]))
    new_fields = compute_row_fields(new["medal"], new["rank"], new["xp"], new["mission"], prev_abs)

    if new_fields["reduced_xp"] > REDUCED_XP_WARN:
        console.print(
            f"[yellow]⚠  Reduced XP is [bold]{new_fields['reduced_xp']}[/bold] "
            f"(threshold: {REDUCED_XP_WARN}). A lot of XP earned at 0.175x rate.[/yellow]"
        )
        if not _confirm("Save anyway? (yes/no)"):
            console.print("[red]Update cancelled.[/red]"); return

    # ── Cascade to next week ──
    next_w   = str(w + 1)
    next_row = data.get(next_w)
    next_fields = compute_row_fields(
        next_row["medal"], next_row["rank"], next_row["xp"],
        next_row["mission_actual"], new_fields["abs_xp"]
    ) if next_row else None

    # ── Build after-state ──
    data_after = {k: dict(v) for k, v in data.items()}
    data_after[str(w)].update(new_fields)
    if next_fields:
        data_after[next_w].update(next_fields)

    # ── Preview ──
    if w != cur_w:
        affected = [x for x in [w - 1, w, w + 1] if str(x) in data or x == w]
        print_before_after(data, data_after, affected)
    else:
        console.print("\n[bold]Preview:[/bold]")
        for k, v in new_fields.items():
            old_v = row.get(k)
            if v != old_v:
                if isinstance(v, (int, float)) and isinstance(old_v, (int, float)):
                    delta = v - old_v
                    sign  = "+" if delta >= 0 else ""
                    diff  = f" [yellow]({sign}{delta})[/yellow]"
                else:
                    diff = ""
                console.print(f"  {k}: [dim]{old_v}[/dim] → [green]{v}[/green]{diff}")

    # ── Save ──
    data[str(w)].update(new_fields)
    if next_fields and next_row:
        data[next_w].update(next_fields)
    save(data)
    console.print(
        f"\n[green]✓ Saved:[/green] Week: {w} | "
        f"Medal: {new['medal']} | Rank: {new['rank']} | XP: {new['xp']} | Mission: {new['mission']}"
    )

# ═══════════════════════════════════════════
# DELETE
# ═══════════════════════════════════════════

def run_delete(week_range=None):
    data = load()
    if not data:
        console.print("[dim]No data to delete.[/dim]"); return

    if week_range is None:
        existing_weeks = sorted(int(k) for k in data)
        console.print(f"[dim]Existing weeks: {fmt_range(existing_weeks)}[/dim]")
        raw = input("Week(s) to delete (e.g. 5 or 3-7): ").strip()
        week_range = parse_week_range(raw)
        if week_range is None:
            console.print("[red]Invalid range. Use '5' or '3-7'.[/red]"); return

    to_del   = [w for w in week_range if str(w) in data]
    missing  = [w for w in week_range if str(w) not in data]

    if not to_del:
        existing_weeks = sorted(int(k) for k in data)
        console.print(f"[red]None of those weeks exist. Existing: {fmt_range(existing_weeks)}[/red]")
        return
    if missing:
        console.print(f"[yellow]⚠  Weeks not found (skipped): {fmt_range(missing)}[/yellow]")

    # ── Build after-state ──
    data_after = {k: dict(v) for k, v in data.items()}
    for w in to_del:
        del data_after[str(w)]

    # ── Find first surviving next week for cascade preview ──
    first_next = next((w for w in sorted(data_after, key=int)
                       if int(w) > max(to_del)), None)

    # ── Affected range for before/after: to_del + one week before + first_next ──
    display_set = set(to_del)
    min_del = min(to_del)
    if str(min_del - 1) in data:
        display_set.add(min_del - 1)
    if first_next:
        display_set.add(int(first_next))

    print_before_after(data, data_after, sorted(display_set))

    label = fmt_range(to_del)
    console.print(f"[yellow]⚠  Delete week(s) {label}? (yes/no)[/yellow]")
    if not _confirm():
        console.print("[dim]Cancelled.[/dim]"); return

    for w in to_del:
        del data[str(w)]
    save(data)
    console.print(f"[yellow]Deleted week(s): {label}[/yellow]")

# ═══════════════════════════════════════════
# TABLE
# ═══════════════════════════════════════════

def build_projection(data, weekly_cap=None):
    """Project weekly XP to year-end.

    weekly_cap: if None, assumes overload (full basic XP cap) + full mission
    each week, same as before. If given, it's an abs_xp amount earned each
    week (mission XP included) — used to model a player who can't/won't grind
    a full overload week. The full mission XP is still always credited first
    (it's "free"), and whatever's left of the cap is converted into basic XP
    via the normal XP curve (reverse_basic_from_total), capped at BASIC_CAP.
    """
    if not data:
        return {}
    last_w   = max(int(k) for k in data)
    prev_abs = data[str(last_w)]["abs_xp"]
    proj     = {}
    cap_xp, _, _ = compute_xp(BASIC_CAP)
    for w in range(last_w + 1, last_week_of_year() + 1):
        mm = mission_max(w)

        if weekly_cap is None:
            gained_total = cap_xp + mm
            basic        = BASIC_CAP
            reduced      = 0
            mission_a    = mm
        else:
            gained_total = max(0, weekly_cap)
            mission_a    = min(mm, gained_total)
            remaining    = max(0, gained_total - mission_a)
            # Convert remaining (post-mission) XP into basic XP via the curve,
            # capping basic XP at BASIC_CAP (can't exceed normal weekly cap).
            basic_uncapped = reverse_basic_from_total(remaining)
            basic          = min(basic_uncapped, BASIC_CAP)
            _, reduced, _  = compute_xp(basic)

        new_abs = prev_abs + gained_total
        si, ei  = get_week_dates_iso(w)
        m, r, x = abs_to_mrx(new_abs)
        proj[str(w)] = {
            "abs_xp": new_abs, "medal": m, "rank": r, "xp": x,
            "basic_xp": int(basic), "reduced_xp": int(reduced),
            "mission_actual": mission_a, "mission_max": mm,
            "date_start": si, "date_end": ei,
        }
        prev_abs = new_abs
    return proj

def run_table(mode="existing", week_range=None, weekly_cap=None):
    """
    mode: "existing" | "projected" | "full" | "auto"
    When week_range spans both real and projected weeks, auto-prints both tables.
    weekly_cap: optional abs_xp amount earned per week, used for projected weeks
    (see build_projection). None = default overload assumption.
    """
    data = load()
    proj = build_projection(data, weekly_cap=weekly_cap)

    def filter_w(d):
        if week_range is None:
            return d
        return {k: v for k, v in d.items() if int(k) in week_range}

    real_rows = filter_w(data)
    proj_rows = filter_w(proj)

    proj_title = (
        "CS2 XP – Projected Data (overload each week)" if weekly_cap is None
        else f"CS2 XP – Projected Data ({weekly_cap} abs XP/week)"
    )

    # "auto" mode: if a range is given that covers both real and projected, show both
    if mode == "existing":
        if real_rows:
            print_data_table(real_rows, "CS2 XP – Recorded Data")
        else:
            console.print("[dim]No recorded data for those weeks.[/dim]")

    elif mode == "projected":
        if proj_rows:
            print_data_table(proj_rows, proj_title)
        else:
            console.print("[dim]No projected data for those weeks.[/dim]")

    elif mode == "full":
        if real_rows:
            print_data_table(real_rows, "CS2 XP – Recorded Data")
        else:
            console.print("[dim]No recorded data for those weeks.[/dim]")
        if proj_rows:
            print_data_table(proj_rows, proj_title)
        else:
            console.print("[dim]No projected data for those weeks.[/dim]")

    elif mode == "auto":
        # When a week range spans real + projected weeks: show both tables
        if real_rows and proj_rows:
            print_data_table(real_rows, "CS2 XP – Recorded Data")
            print_data_table(proj_rows, proj_title)
        elif real_rows:
            print_data_table(real_rows, "CS2 XP – Recorded Data")
        elif proj_rows:
            print_data_table(proj_rows, proj_title)
        else:
            console.print("[dim]No data for those weeks.[/dim]")

# ═══════════════════════════════════════════
# HELP
# ═══════════════════════════════════════════

HELP_TEXT = f"""[bold cyan]{APP_NAME}[/bold cyan] [dim]v{__version__}[/dim] — Help

[bold]Commands[/bold]

  [cyan]status[/cyan] / [cyan]s[/cyan] / [cyan]stat[/cyan]
      Show XP progress for the current week.
      [cyan]-week N[/cyan] / [cyan]-w N[/cyan]   Show a specific week instead.
      [cyan]-full[/cyan] / [cyan]-f[/cyan]         Alias (same as no argument).

  [cyan]update[/cyan] / [cyan]u[/cyan] / [cyan]upd[/cyan]
      Update week data. Default / [cyan]-full[/cyan] / [cyan]-f[/cyan]: asks week, medal, rank, xp, mission.
      Past weeks show a before/after preview before saving.
      [cyan]-medal[/cyan] / [cyan]-med[/cyan]      Ask medal, rank, xp   (current week).
      [cyan]-rank[/cyan]  / [cyan]-r[/cyan]          Ask rank, xp           (current week).
      [cyan]-xp[/cyan]                  Ask xp only            (current week).
      [cyan]-mission[/cyan] / [cyan]-mis[/cyan]   Ask mission XP only    (current week).
      [bold yellow]⚠[/bold yellow] reduced_xp > {REDUCED_XP_WARN} triggers a warning before saving.

  [cyan]delete[/cyan] / [cyan]d[/cyan] / [cyan]del[/cyan]  [N | N-M]
      Delete week(s). Accepts single week or range: [cyan]d 5[/cyan]  [cyan]d 3-10[/cyan]
      If no range given in command, prompts (shows existing weeks first).
      Shows before/after preview including the first surviving next week.
      [cyan]-full[/cyan] / [cyan]-f[/cyan]         Alias (same as no argument).

  [cyan]table[/cyan] / [cyan]t[/cyan]  [N | N-M]
      Display all recorded data. Optionally filter: [cyan]t 5[/cyan]  [cyan]t 1-10[/cyan]
      When range spans real + projected weeks, both tables are shown automatically.
      [cyan]-existing[/cyan] / [cyan]-e[/cyan]     Only recorded weeks (default).
      [cyan]-projected[/cyan] / [cyan]-p[/cyan]    Only projected weeks (overload each week to year-end).
      [cyan]-projected N[/cyan] / [cyan]-p N[/cyan]  Same, but assumes only N abs XP earned each week
                              instead of a full overload week. Useful if you can't/won't
                              grind a full week and want to see the realistic medal pace.
                              Mission XP is still credited first each week (it's free);
                              N just caps the total (mission + basic) XP earned that week.
                              If N omitted, falls back to the default overload assumption.
      [cyan]-full[/cyan] / [cyan]-f[/cyan]          Both recorded and projected.
      Examples: [cyan]t[/cyan]  [cyan]t -f[/cyan]  [cyan]t 1-10[/cyan]  [cyan]t -p 3-8[/cyan]  [cyan]t -p 1000[/cyan]

  [cyan]build[/cyan] / [cyan]b[/cyan]
      Compile cs2xp.py into a standalone .exe using PyInstaller.
      The .exe is placed in the same folder as this script.
      All temporary build files are automatically deleted afterwards.
      PyInstaller is installed automatically if not already present.

  [cyan]upgrade[/cyan] / [cyan]upg[/cyan]
      Check GitHub for a newer release and install it in place.
      Downloads the matching asset (.exe when running compiled, .py otherwise),
      swaps it in, and restarts. Shows release notes before asking to confirm.

  [cyan]locate[/cyan] / [cyan]loc[/cyan]
      Show where the program is running from and where its data file is stored.

  [cyan]help[/cyan] / [cyan]h[/cyan]
      Show this help message.
      [cyan]-full[/cyan] / [cyan]-f[/cyan]         Alias (same as no argument).

  [cyan]exit[/cyan] / [cyan]quit[/cyan] / [cyan]stop[/cyan] / [cyan]e[/cyan] / [cyan]q[/cyan]
      Exit the tracker.

[bold]Notes[/bold]
  Commands and arguments are case-insensitive.
  Press Enter at any prompt to keep the current stored value.
  Editing a past week cascades recalculation into the following week.
  XP total cannot be lower than the previous week's abs_xp."""

def run_help():
    console.print(Panel(HELP_TEXT, expand=False))

# ═══════════════════════════════════════════
# COMMAND PARSING
# ═══════════════════════════════════════════

_VERBS = {
    "status": "status", "s":    "status", "stat": "status",
    "update": "update", "u":    "update", "upd":  "update",
    "delete": "delete", "d":    "delete", "del":  "delete",
    "table":  "table",  "t":    "table",
    "help":   "help",   "h":    "help",
    "build":  "build",  "b":    "build",
    "upgrade": "upgrade", "upg": "upgrade",
    "locate":  "locate",  "loc": "locate",
    "exit":   "exit",   "quit": "exit",   "stop": "exit",
    "e":      "exit",   "q":    "exit",
}

# Args that set a named mode per command
_CMD_MODES = {
    "update": {
        "-full": "full", "-f": "full",
        "-medal": "medal", "-med": "medal",
        "-rank":  "rank",  "-r":   "rank",
        "-xp":    "xp",
        "-mission": "mission", "-mis": "mission",
    },
    "table": {
        "-existing": "existing", "-e": "existing",
        "-projected": "projected", "-p": "projected",
        "-full": "full", "-f": "full",
    },
    # -full / -f accepted but ignored on these (no-op alias)
    "status": {"-full": None, "-f": None, "-week": "_week", "-w": "_week"},
    "delete": {"-full": None, "-f": None},
    "help":   {"-full": None, "-f": None},
    "build":  {},
    "upgrade": {},
    "locate":  {},
}

_DEFAULT_MODES = {
    "update": "full",
    "table":  "existing",
}

def parse_command(raw: str):
    """Returns (cmd, mode, week, week_range, weekly_cap, error) — all Nones on empty input."""
    parts = raw.strip().lower().split()
    if not parts:
        return None, None, None, None, None, None

    verb = parts[0]
    cmd  = _VERBS.get(verb)
    if cmd is None:
        return None, None, None, None, None, f"[red]Unknown command '{verb}'. Type 'help'.[/red]"

    valid_flags = _CMD_MODES.get(cmd, {})
    args        = parts[1:]
    mode        = None
    week        = None
    week_range  = None
    weekly_cap  = None
    i           = 0

    while i < len(args):
        a = args[i]

        # Flagged args
        if a in valid_flags:
            mapped = valid_flags[a]
            if mapped == "_week":
                # Consume next token as week number
                if i + 1 >= len(args):
                    return None, None, None, None, None, f"[red]{a} requires a week number.[/red]"
                try:
                    week = int(args[i + 1])
                except ValueError:
                    return None, None, None, None, None, f"[red]{a} requires an integer.[/red]"
                i += 2; continue
            elif mapped is not None:
                mode = mapped
                # -projected / -p may optionally be followed by an integer:
                # the abs_xp amount earned per week, to use instead of the
                # default overload assumption when building the projection.
                if mapped == "projected" and i + 1 < len(args):
                    nxt = args[i + 1]
                    if nxt.lstrip("-").isdigit():
                        weekly_cap = int(nxt)
                        i += 2; continue
            i += 1; continue

        # Universal -full / -f on any command (no-op if not in valid_flags already)
        if a in ("-full", "-f") and cmd != "exit":
            if cmd in ("update", "table"):
                mode = "full"
            i += 1; continue

        # Unknown flag
        if a.startswith("-"):
            valids = "  ".join(valid_flags) if valid_flags else "(none)"
            return None, None, None, None, None, (
                f"[red]Unknown argument '{a}' for '{verb}'.[/red]\n"
                f"[dim]Valid: {valids}[/dim]"
            )

        # Positional: week range for table and delete
        if cmd in ("table", "delete") and week_range is None:
            wr = parse_week_range(a)
            if wr is not None:
                week_range = wr; i += 1; continue

        return None, None, None, None, None, f"[red]Unexpected token '{a}' for '{verb}'. Type 'help'.[/red]"

    mode = mode or _DEFAULT_MODES.get(cmd)
    return cmd, mode, week, week_range, weekly_cap, None

# ═══════════════════════════════════════════
# BUILD EXE
# ═══════════════════════════════════════════

def run_build():
    """Create a single-file .exe via PyInstaller, then clean up all build artefacts."""
    if IS_FROZEN:
        console.print("[yellow]Build is not available when running as a compiled .exe.[/yellow]")
        return
    import subprocess, shutil, tempfile

    script = Path(__file__).resolve()
    out_dir = script.parent

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        console.print("[yellow]PyInstaller not found. Installing…[/yellow]")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        console.print("[green]PyInstaller installed.[/green]")

    console.print(f"[cyan]Building {script.stem}.exe → {out_dir}[/cyan]")

    # Use a temp dir for ALL PyInstaller work so nothing leaks into the project folder
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--noconfirm",
            "--clean",
            f"--distpath={out_dir}",   # .exe lands directly in the script folder
            f"--workpath={tmp}",        # build/ goes into the temp dir
            f"--specpath={tmp}",        # .spec file goes into the temp dir
            str(script),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            console.print("[red]Build failed:[/red]")
            console.print(result.stderr[-3000:])  # last 3 000 chars of stderr
            return

    # Any stray build/ or dist/ folders that PyInstaller may have created beside the script
    for artefact in ("build", "__pycache__"):
        p = out_dir / artefact
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    exe_name = script.stem + (".exe" if sys.platform == "win32" else "")
    exe_path = out_dir / exe_name
    if exe_path.exists():
        console.print(f"[green]✓ Built:[/green] {exe_path}")
    else:
        console.print(f"[yellow]Build finished but {exe_path} not found — check output above.[/yellow]")

# ═══════════════════════════════════════════
# UPGRADE APP (self-update)
# ═══════════════════════════════════════════

def _parse_version(v):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3) for comparison. Non-numeric parts become 0."""
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)

def _fetch_latest_release():
    """Returns the parsed JSON of the latest GitHub release, or None on failure."""
    import urllib.request, urllib.error

    req = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={"Accept": "application/vnd.github+json", "User-Agent": APP_NAME},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        console.print(f"[red]GitHub API error: {e.code} {e.reason}[/red]")
    except urllib.error.URLError as e:
        console.print(f"[red]Network error reaching GitHub: {e.reason}[/red]")
    except Exception as e:
        console.print(f"[red]Could not check for updates: {e}[/red]")
    return None

def _pick_asset(release):
    """Pick the right release asset for this platform: .exe on Windows when frozen,
    otherwise fall back to a .py asset (or the source .zip GitHub always provides)."""
    assets = release.get("assets", [])
    if IS_FROZEN and sys.platform == "win32":
        for a in assets:
            if a["name"].lower().endswith(".exe"):
                return a
    for a in assets:
        if a["name"].lower().endswith(".py"):
            return a
    return None

def run_upgrade():
    """Check GitHub Releases for a newer version and, if found, download and
    install it in place — replacing the running .exe (via a swap-on-restart
    helper script) or the running .py file directly."""
    console.print(f"[cyan]Current version:[/cyan] {__version__}")
    console.print("[dim]Checking GitHub for the latest release…[/dim]")

    release = _fetch_latest_release()
    if release is None:
        return

    latest_tag = release.get("tag_name", "")
    latest_ver = _parse_version(latest_tag)
    cur_ver    = _parse_version(__version__)

    if latest_ver <= cur_ver:
        console.print(f"[green]✓ You're up to date.[/green] (latest: {latest_tag or __version__})")
        return

    console.print(f"[yellow]New version available:[/yellow] {latest_tag}  (you have {__version__})")
    notes = (release.get("body") or "").strip()
    if notes:
        console.print(Panel(notes[:1500], title="Release notes", expand=False))

    asset = _pick_asset(release)
    if asset is None:
        console.print(
            "[yellow]No matching downloadable asset found in the release.[/yellow]\n"
            f"[dim]You can grab it manually: {release.get('html_url', GITHUB_API_LATEST)}[/dim]"
        )
        return

    if not _confirm(f"Download and install {asset['name']}? (yes/no)"):
        console.print("[dim]Upgrade cancelled.[/dim]"); return

    import urllib.request, tempfile, shutil

    dest_dir = app_dir()
    tmp_path = Path(tempfile.gettempdir()) / asset["name"]

    console.print(f"[cyan]Downloading {asset['name']}…[/cyan]")
    try:
        urllib.request.urlretrieve(asset["browser_download_url"], tmp_path)
    except Exception as e:
        console.print(f"[red]Download failed: {e}[/red]")
        return

    if IS_FROZEN and sys.platform == "win32" and tmp_path.suffix.lower() == ".exe":
        # Windows won't let a running .exe overwrite itself. Spin up a small
        # batch helper that waits for this process to exit, swaps the file
        # in, then relaunches it.
        current_exe = Path(sys.executable).resolve()
        bat_path    = Path(tempfile.gettempdir()) / "cs2xp_upgrade.bat"
        bat_path.write_text(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'move /y "{tmp_path}" "{current_exe}"\r\n'
            f'start "" "{current_exe}"\r\n'
            "del \"%~f0\"\r\n"
        )
        console.print("[green]✓ Update downloaded.[/green] Restarting to finish installing…")
        import subprocess
        subprocess.Popen(["cmd", "/c", str(bat_path)],
                          creationflags=subprocess.CREATE_NEW_CONSOLE)
        sys.exit(0)
    else:
        # Running as a plain .py script — overwrite it directly, safe to do
        # while running on POSIX, and the only sane option cross-platform too.
        target = Path(__file__).resolve()
        shutil.move(str(tmp_path), str(target))
        console.print(f"[green]✓ Updated {target.name} to {latest_tag}.[/green] Restart the app to use the new version.")

# ═══════════════════════════════════════════
# LOCATE
# ═══════════════════════════════════════════

def run_locate():
    """Show where the program is running from and where its data file lives."""
    prog_path = Path(sys.executable).resolve() if IS_FROZEN else Path(__file__).resolve()
    kind      = "compiled .exe" if IS_FROZEN else "Python script"

    console.print("[bold]Locations[/bold]")
    console.print(f"  Program   : {prog_path}  [dim]({kind})[/dim]")
    console.print(f"  App folder: {app_dir()}")
    console.print(f"  Data file : {DATA_FILE}  [dim]({'exists' if DATA_FILE.exists() else 'not created yet'})[/dim]")

# ═══════════════════════════════════════════
# INTERACTIVE LOOP
# ═══════════════════════════════════════════

def interactive():
    console.print(Panel.fit(
        f"[bold cyan]{APP_NAME}[/bold cyan] [dim]v{__version__}[/dim]\n"
        "Tracks your weekly CS2 XP progress.\n\n"
        "Start with: [cyan]status[/cyan]  [cyan]update[/cyan]  [cyan]help[/cyan]"
    ))

    while True:
        try:
            raw = (pt_prompt("[cs2xp] > ", history=_PT_HISTORY) if USE_PROMPT_TOOLKIT else input("[cs2xp] > ")).strip()
            if not raw:
                continue

            cmd, mode, week, week_range, weekly_cap, err = parse_command(raw)
            if err:
                console.print(err); continue
            if cmd is None:
                continue

            if   cmd == "exit":   console.print("[dim]Session closed.[/dim]"); break
            elif cmd == "status": run_status(target_week=week)
            elif cmd == "update": run_update(mode=mode or "full")
            elif cmd == "delete": run_delete(week_range=week_range)
            elif cmd == "build":
                if IS_FROZEN:
                    console.print("[yellow]Build is not available when running as a compiled .exe.[/yellow]")
                else:
                    run_build()
            elif cmd == "upgrade": run_upgrade()
            elif cmd == "locate":  run_locate()
            elif cmd == "table":
                # Auto-detect mixed real/projected range
                eff_mode = mode or "existing"
                if week_range and eff_mode == "existing":
                    eff_mode = "auto"
                run_table(mode=eff_mode, week_range=week_range, weekly_cap=weekly_cap)
            elif cmd == "help":   run_help()

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session closed.[/dim]"); break
        except Exception as ex:
            console.print(f"[red]Error: {ex}[/red]")


if __name__ == "__main__":
    interactive()
