import json
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
DATA_FILE = Path("cs2xp.json")

# ═══════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════

XP_PER_RANK  = 5000
RANKS_MEDAL  = 39
XP_PER_MEDAL = XP_PER_RANK * RANKS_MEDAL

# Each entry: (basic_xp_cap_for_stage | None, multiplier, label)
# Last stage has no cap — continues indefinitely.
XP_STAGES = [
    (1125, 4,     "4x"),
    (1500, 2,     "2x"),
    (3667, 1,     "1x"),
    (None, 0.175, "0.175x"),
]

# Derived cumulative thresholds
BASIC_4X     = XP_STAGES[0][0]                     # 1125
BASIC_2X     = XP_STAGES[1][0]                     # 1500
BASIC_1X     = XP_STAGES[2][0]                     # 3667
BASIC_CAP    = BASIC_4X + BASIC_2X + BASIC_1X      # 6292
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

def week_now():
    shifted = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    return max(1, (shifted.date() - FIRST_WED).days // 7 + 1)

def get_week_dates(week):
    start = FIRST_WED + datetime.timedelta(days=(week - 1) * 7)
    return start, min(start + datetime.timedelta(days=6), YEAR_END)

def get_week_dates_iso(week):
    s, e = get_week_dates(week)
    return s.isoformat(), e.isoformat()

def time_left_in_week(week):
    _, end = get_week_dates(week)
    end_dt = datetime.datetime(end.year, end.month, end.day, 23, 59, 59,
                               tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
    now    = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=1)))
    return max(datetime.timedelta(0), end_dt - now)

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
    """Returns (total_xp_gained, reduced_xp, stage_label)."""
    cum, total = 0, 0
    for cap, mult, label in XP_STAGES:
        if cap is None:
            extra = basic - cum
            red   = extra * mult
            return total + red, red, label
        into = min(basic - cum, cap)
        if into <= 0:
            return total, 0, label
        total += into * mult
        cum   += cap
        if basic <= cum:
            return total, 0, label
    return total, 0, XP_STAGES[-1][2]

def reverse_basic_from_total(total_xp):
    cum, rem = 0, total_xp
    for cap, mult, _ in XP_STAGES:
        if cap is None:
            return cum + rem / mult
        stage_total = cap * mult
        if rem <= stage_total:
            return cum + rem / mult
        rem -= stage_total
        cum += cap
    return cum

def stage_at_basic(basic):
    """Returns (label, basic_into_stage, stage_cap_or_None)."""
    cum = 0
    for cap, mult, label in XP_STAGES:
        if cap is None or basic <= cum + cap:
            return label, basic - cum, cap
        cum += cap
    return XP_STAGES[-1][2], basic - BASIC_CAP, None

def stage_boundary_basic(basic):
    """Cumulative basic XP at end of current stage, or None if in final stage."""
    cum = 0
    for cap, mult, label in XP_STAGES:
        boundary = cum + (cap or 0)
        if cap is None or basic <= boundary:
            return boundary if cap is not None else None
        cum += cap
    return None

def next_stage_label(current_label):
    for i, (_, _, lbl) in enumerate(XP_STAGES):
        if lbl == current_label and i + 1 < len(XP_STAGES):
            return XP_STAGES[i + 1][2]
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
    nums = [f"{int(into)}/{scap or '∞'}", f"{int(basic)}/{t1}", f"{m_cur}/{m_max}"]
    pcts = [
        f"({into/scap*100:.1f}%)" if scap else "(overload)",
        f"({basic/t1*100:.1f}%)",
        f"({m_cur/m_max*100:.1f}%)" if m_max else "(0.0%)",
    ]
    WN = max(len(s) for s in nums)
    WP = max(len(s) for s in pcts)

    console.print("\n[bold]XP Progress[/bold]")
    console.print(f"  Stage XP   : {nums[0]:<{WN}} {pcts[0]:<{WP}} {bar(into, scap or basic)}")
    console.print(f"  Total XP   : {nums[1]:<{WN}} {pcts[1]:<{WP}} {bar(basic, t1)}")
    console.print(f"  Mission XP : {nums[2]:<{WN}} {pcts[2]:<{WP}} {bar(m_cur, m_max)}")

    # ── Per-stage breakdown ──
    console.print(f"\n[bold green]Current Stage:[/bold green] {stage}")
    cum = 0
    for cap, mult, label in XP_STAGES:
        if cap is None:
            if stage == label:
                extra = basic - BASIC_CAP
                _, red, _ = compute_xp(basic)
                console.print(f"  {label}: Earned: {int(red)} XP (~{int(extra)} Basic XP)")
            break
        earned_b = max(0, min(basic - cum, cap))
        earned_x = int(earned_b * mult)
        is_cur   = (stage == label)
        not_yet  = (basic <= cum)
        if is_cur:
            left_b, left_x = int(cap - earned_b), int((cap - earned_b) * mult)
            console.print(f"  {label}: Earned: {earned_x} XP ({int(earned_b)} Basic XP) | Left: {left_x} XP ({left_b} Basic XP)")
        elif not_yet:
            console.print(f"  [dim]{label}: Left: {int(cap*mult)} XP ({cap} Basic XP)[/dim]")
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

    dm_played_c,   dm_need_c   = playtime_row("DM",   basic, rem1)
    comp_played_c, comp_need_c = playtime_row("Comp", basic, rem1)
    all_cells = [dm_played_c, dm_need_c, comp_played_c, comp_need_c]

    gs = [f"{c[0]:.1f}" for c in all_cells]
    ms = [f"{c[1]:.1f}" for c in all_cells]
    hs = [f"{c[2]:.1f}" for c in all_cells]
    WG, WM, WH = max(len(s) for s in gs), max(len(s) for s in ms), max(len(s) for s in hs)

    def pt(i):
        return f"{gs[i]:>{WG}} (~{ms[i]:>{WM}} min or ~{hs[i]:>{WH}} hr)"

    console.print("\n[bold]Playtime Estimation[/bold]")
    console.print(f"  DM   : Played: {pt(0)}  |  Left: {pt(1)}")
    console.print(f"  Comp : Played: {pt(2)}  |  Left: {pt(3)}")

    # ── Rank-up / weekly drop ──
    is_weekly = (row["rank"] == prev["rank"] and row["medal"] == prev["medal"])
    xp_needed = XP_PER_RANK - row["xp"]
    console.print("\n[bold]To Weekly Drop[/bold]" if is_weekly else "\n[bold]To Rank-Up[/bold]")

    def simulate_basic_needed(xp_target):
        sb, sx = basic, 0
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
        console.print(f"  Left without mission : ~{int(basic_nm)} Basic XP | {playtime_line(basic_nm)}")
        console.print(f"  Left with mission    : ~{int(basic_m)} Basic XP | {playtime_line(basic_m)}")
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
                console.print(f"  {k}: [dim]{old_v}[/dim] → [green]{v}[/green]")

    # ── Save ──
    data[str(w)].update(new_fields)
    if next_fields and next_row:
        data[next_w].update(next_fields)
    save(data)
    console.print(
        f"[green]✓ Saved:[/green] Week: {w} | "
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

def build_projection(data):
    """Project weekly XP to year-end, assuming overload + full mission each week."""
    if not data:
        return {}
    last_w   = max(int(k) for k in data)
    prev_abs = data[str(last_w)]["abs_xp"]
    proj     = {}
    cap_xp, _, _ = compute_xp(BASIC_CAP)
    for w in range(last_w + 1, last_week_of_year() + 1):
        mm      = mission_max(w)
        new_abs = prev_abs + cap_xp + mm
        si, ei  = get_week_dates_iso(w)
        m, r, x = abs_to_mrx(new_abs)
        proj[str(w)] = {
            "abs_xp": new_abs, "medal": m, "rank": r, "xp": x,
            "basic_xp": BASIC_CAP, "reduced_xp": 0,
            "mission_actual": mm, "mission_max": mm,
            "date_start": si, "date_end": ei,
        }
        prev_abs = new_abs
    return proj

def run_table(mode="existing", week_range=None):
    """
    mode: "existing" | "projected" | "full" | "auto"
    When week_range spans both real and projected weeks, auto-prints both tables.
    """
    data = load()
    proj = build_projection(data)

    def filter_w(d):
        if week_range is None:
            return d
        return {k: v for k, v in d.items() if int(k) in week_range}

    real_rows = filter_w(data)
    proj_rows = filter_w(proj)

    # "auto" mode: if a range is given that covers both real and projected, show both
    if mode == "existing":
        if real_rows:
            print_data_table(real_rows, "CS2 XP – Recorded Data")
        else:
            console.print("[dim]No recorded data for those weeks.[/dim]")

    elif mode == "projected":
        if proj_rows:
            print_data_table(proj_rows, "CS2 XP – Projected Data (overload each week)")
        else:
            console.print("[dim]No projected data for those weeks.[/dim]")

    elif mode == "full":
        if real_rows:
            print_data_table(real_rows, "CS2 XP – Recorded Data")
        else:
            console.print("[dim]No recorded data for those weeks.[/dim]")
        if proj_rows:
            print_data_table(proj_rows, "CS2 XP – Projected Data (overload each week)")
        else:
            console.print("[dim]No projected data for those weeks.[/dim]")

    elif mode == "auto":
        # When a week range spans real + projected weeks: show both tables
        if real_rows and proj_rows:
            print_data_table(real_rows, "CS2 XP – Recorded Data")
            print_data_table(proj_rows, "CS2 XP – Projected Data (overload each week)")
        elif real_rows:
            print_data_table(real_rows, "CS2 XP – Recorded Data")
        elif proj_rows:
            print_data_table(proj_rows, "CS2 XP – Projected Data (overload each week)")
        else:
            console.print("[dim]No data for those weeks.[/dim]")

# ═══════════════════════════════════════════
# HELP
# ═══════════════════════════════════════════

HELP_TEXT = f"""[bold cyan]CS2 XP Tracker — Help[/bold cyan]

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
      [cyan]-full[/cyan] / [cyan]-f[/cyan]          Both recorded and projected.
      Examples: [cyan]t[/cyan]  [cyan]t -f[/cyan]  [cyan]t 1-10[/cyan]  [cyan]t -p 3-8[/cyan]

  [cyan]build[/cyan] / [cyan]b[/cyan]
      Compile cs2xp.py into a standalone .exe using PyInstaller.
      The .exe is placed in the same folder as this script.
      All temporary build files are automatically deleted afterwards.
      PyInstaller is installed automatically if not already present.

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
}

_DEFAULT_MODES = {
    "update": "full",
    "table":  "existing",
}

def parse_command(raw: str):
    """Returns (cmd, mode, week, week_range, error) — all Nones on empty input."""
    parts = raw.strip().lower().split()
    if not parts:
        return None, None, None, None, None

    verb = parts[0]
    cmd  = _VERBS.get(verb)
    if cmd is None:
        return None, None, None, None, f"[red]Unknown command '{verb}'. Type 'help'.[/red]"

    valid_flags = _CMD_MODES.get(cmd, {})
    args        = parts[1:]
    mode        = None
    week        = None
    week_range  = None
    i           = 0

    while i < len(args):
        a = args[i]

        # Flagged args
        if a in valid_flags:
            mapped = valid_flags[a]
            if mapped == "_week":
                # Consume next token as week number
                if i + 1 >= len(args):
                    return None, None, None, None, f"[red]{a} requires a week number.[/red]"
                try:
                    week = int(args[i + 1])
                except ValueError:
                    return None, None, None, None, f"[red]{a} requires an integer.[/red]"
                i += 2; continue
            elif mapped is not None:
                mode = mapped
            i += 1; continue

        # Universal -full / -f on any command (no-op if not in valid_flags already)
        if a in ("-full", "-f") and cmd != "exit":
            if cmd in ("update", "table"):
                mode = "full"
            i += 1; continue

        # Unknown flag
        if a.startswith("-"):
            valids = "  ".join(valid_flags) if valid_flags else "(none)"
            return None, None, None, None, (
                f"[red]Unknown argument '{a}' for '{verb}'.[/red]\n"
                f"[dim]Valid: {valids}[/dim]"
            )

        # Positional: week range for table and delete
        if cmd in ("table", "delete") and week_range is None:
            wr = parse_week_range(a)
            if wr is not None:
                week_range = wr; i += 1; continue

        return None, None, None, None, f"[red]Unexpected token '{a}' for '{verb}'. Type 'help'.[/red]"

    mode = mode or _DEFAULT_MODES.get(cmd)
    return cmd, mode, week, week_range, None

# ═══════════════════════════════════════════
# BUILD EXE
# ═══════════════════════════════════════════

def run_build():
    """Create a single-file .exe via PyInstaller, then clean up all build artefacts."""
    import subprocess, sys, shutil, tempfile

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
# INTERACTIVE LOOP
# ═══════════════════════════════════════════

def interactive():
    console.print(Panel.fit(
        "[bold cyan]🎯 CS2 XP Tracker[/bold cyan]\n\n"
        "Track your weekly XP progress in CS2.\n\n"
        "  [cyan]s[/cyan]       – status (current week)\n"
        "  [cyan]u[/cyan]       – update XP\n"
        "  [cyan]t[/cyan]       – table of all weeks\n"
        "  [cyan]t -f[/cyan]    – table + projection\n"
        "  [cyan]t 1-10[/cyan]  – filter by week range\n"
        "  [cyan]d 3-7[/cyan]   – delete week range\n"
        "  [cyan]b[/cyan]       – build standalone .exe\n"
        "  [cyan]h[/cyan]       – help\n"
        "  [cyan]e[/cyan]       – exit"
    ))

    while True:
        try:
            raw = (pt_prompt("[cs2xp] > ", history=_PT_HISTORY) if USE_PROMPT_TOOLKIT else input("[cs2xp] > ")).strip()
            if not raw:
                continue

            cmd, mode, week, week_range, err = parse_command(raw)
            if err:
                console.print(err); continue
            if cmd is None:
                continue

            if   cmd == "exit":   console.print("[dim]Session closed.[/dim]"); break
            elif cmd == "status": run_status(target_week=week)
            elif cmd == "update": run_update(mode=mode or "full")
            elif cmd == "delete": run_delete(week_range=week_range)
            elif cmd == "build":  run_build()
            elif cmd == "table":
                # Auto-detect mixed real/projected range
                eff_mode = mode or "existing"
                if week_range and eff_mode == "existing":
                    eff_mode = "auto"
                run_table(mode=eff_mode, week_range=week_range)
            elif cmd == "help":   run_help()

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session closed.[/dim]"); break
        except Exception as ex:
            console.print(f"[red]Error: {ex}[/red]")


if __name__ == "__main__":
    interactive()
