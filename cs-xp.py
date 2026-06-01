"""
CS2 XP Tracker — Pink Medal by end of 2026
Week resets Wednesday 00:00 UTC (02:00 GMT+2)
"""

import csv
import datetime
import os

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

CSV_FILE = "cs2-xp.csv"
CSV_COLS = ["week", "date_start", "date_end", "mission_xp",
            "medal_lvl", "rank", "xp", "reduced_xp"]

XP_PER_RANK  = 5000
RANKS_MEDAL  = 39          # rank-ups needed per medal (1→40 = 39 ups)
XP_PER_MEDAL = XP_PER_RANK * RANKS_MEDAL   # 195 000

# Basic XP zones (base values before multiplier)
BASIC_4X = 1125   # × 4 = 4 500 raw
BASIC_2X = 1500   # × 2 = 3 000 raw
BASIC_1X = 3667   # × 1 = 3 667 raw
# Total raw XP before overload:
NON_REDUCED_RAW = BASIC_4X * 4 + BASIC_2X * 2 + BASIC_1X   # 11 167

MEDAL_NAME = {0: "None", 1: "Gray", 2: "Green", 3: "Blue",
              4: "Purple", 5: "Pink", 6: "Red"}

# Mission XP repeating 8-week cycle (week 1 = Jan 7)
MISSION_CYCLE = [600, 1050, 1050, 550, 1050, 1050, 600, 1050]

FIRST_WED = datetime.date(2026, 1, 7)   # week 1 start
START_WEEK = 9                          # we begin tracking from week 9

PINK_TARGET = 5 * XP_PER_MEDAL         # 975 000 absolute XP


# ──────────────────────────────────────────────────────────────
# CALENDAR
# ──────────────────────────────────────────────────────────────

def week_start(w: int) -> datetime.date:
    return FIRST_WED + datetime.timedelta(weeks=w - 1)

def week_end(w: int) -> datetime.date:
    return week_start(w) + datetime.timedelta(days=6)

def mission_xp(w: int) -> int:
    return MISSION_CYCLE[(w - 1) % 8]

def all_weeks() -> list[int]:
    weeks = []
    w = START_WEEK
    while week_start(w).year == 2026:
        weeks.append(w)
        w += 1
    return weeks

def current_week() -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    days_since_wed = (now.weekday() - 2) % 7
    last_reset = (now - datetime.timedelta(days=days_since_wed)).date()
    w = (last_reset - FIRST_WED).days // 7 + 1
    return max(START_WEEK, w)

def time_to_reset() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    days_until = (2 - now.weekday()) % 7
    if days_until == 0 and (now.hour, now.minute, now.second) > (0, 0, 0):
        days_until = 7
    nxt = (now + datetime.timedelta(days=days_until)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    s = int((nxt - now).total_seconds())
    return f"{s//3600}h {(s%3600)//60}m"


# ──────────────────────────────────────────────────────────────
# XP MATH
# ──────────────────────────────────────────────────────────────

def to_abs(medal: int, rank: int, xp: int) -> int:
    """Medal/rank/xp → absolute XP from zero."""
    return medal * XP_PER_MEDAL + (rank - 1) * XP_PER_RANK + xp

def from_abs(total: int) -> tuple[int, int, int]:
    """Absolute XP → (medal, rank, xp_in_rank)."""
    medal, rem = divmod(max(0, total), XP_PER_MEDAL)
    rank_extra, xp = divmod(rem, XP_PER_RANK)
    rank = rank_extra + 1
    if rank > 39:
        medal += 1; rank = 1; xp = 0
    return medal, rank, xp

def add_week_xp(abs_xp: int, extra_raw: int, mission: int) -> int:
    """Add one week's XP to absolute total."""
    return abs_xp + extra_raw + mission


# ──────────────────────────────────────────────────────────────
# CSV HELPERS
# ──────────────────────────────────────────────────────────────

def load() -> dict[int, dict]:
    rows = {}
    if not os.path.exists(CSV_FILE):
        return rows
    with open(CSV_FILE, newline="") as f:
        for r in csv.DictReader(f):
            w = int(r["week"])
            rows[w] = {
                "week":       w,
                "date_start": r["date_start"],
                "date_end":   r["date_end"],
                "mission_xp": int(r["mission_xp"]),
                "medal_lvl":  int(r["medal_lvl"]),
                "rank":       int(r["rank"]),
                "xp":         int(r["xp"]),
                "reduced_xp": int(r["reduced_xp"]),
            }
    return rows

def save(rows: dict[int, dict]):
    with open(CSV_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for wn in sorted(rows.keys()):
            w.writerow(rows[wn])

def make_row(w: int, medal: int, rank: int, xp: int,
             reduced: int = 0, miss: int | None = None) -> dict:
    return {
        "week":       w,
        "date_start": week_start(w).isoformat(),
        "date_end":   week_end(w).isoformat(),
        "mission_xp": miss if miss is not None else mission_xp(w),
        "medal_lvl":  medal,
        "rank":       rank,
        "xp":         xp,
        "reduced_xp": reduced,
    }


# ──────────────────────────────────────────────────────────────
# PROJECTION
# ──────────────────────────────────────────────────────────────

def build_projection(start_abs: int, from_week: int, weeks: list[int]) -> dict[int, dict]:
    """
    Build projected rows for all weeks >= from_week.
    Each week adds NON_REDUCED_RAW + mission_xp.
    """
    rows = {}
    cur = start_abs
    for w in weeks:
        if w < from_week:
            continue
        miss = mission_xp(w)
        cur = add_week_xp(cur, NON_REDUCED_RAW, miss)
        medal, rank, xp = from_abs(cur)
        rows[w] = make_row(w, medal, rank, xp, reduced=0, miss=miss)
    return rows


# ──────────────────────────────────────────────────────────────
# DISPLAY
# ──────────────────────────────────────────────────────────────

SEP = "═" * 68
DIV = "─" * 68

def mstr(medal: int) -> str:
    return f"{medal} ({MEDAL_NAME.get(medal, '?')})"

def hm(minutes: float) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m"

def show_week(row: dict, label: str = ""):
    tag = f"  [{label}]" if label else " "
    m, r, x = row["medal_lvl"], row["rank"], row["xp"]
    print(f"{tag} Week {row['week']:>2}  {row['date_start']} – {row['date_end']}"
          f"  │  Medal {mstr(m)}  Rank {r}  XP {x:,}"
          f"  │  Mission {row['mission_xp']:,}  Reduced {row['reduced_xp']:,}")

def print_progress(cur_abs: int, gained_basic: int):
    """Show how far through the basic XP zones we are this week."""
    z4 = min(gained_basic, BASIC_4X)
    z2 = min(max(gained_basic - BASIC_4X, 0), BASIC_2X)
    z1 = min(max(gained_basic - BASIC_4X - BASIC_2X, 0), BASIC_1X)
    total_basic = BASIC_4X + BASIC_2X + BASIC_1X   # 6 292

    left_basic = max(0, total_basic - gained_basic)
    left_raw   = max(0, NON_REDUCED_RAW - (z4 * 4 + z2 * 2 + z1))
    left_pct   = left_basic / total_basic * 100

    ol_medal, ol_rank, ol_xp = from_abs(cur_abs + left_raw)

    print(f"  Basic XP progress this week:")
    print(f"    4x zone:  {z4:,} / {BASIC_4X:,} basic  ({z4*4:,} / {BASIC_4X*4:,} raw)")
    print(f"    2x zone:  {z2:,} / {BASIC_2X:,} basic  ({z2*2:,} / {BASIC_2X*2:,} raw)")
    print(f"    1x zone:  {z1:,} / {BASIC_1X:,} basic  ({z1:,} / {BASIC_1X:,} raw)")
    print(f"  Left until overload:  {left_basic:,} basic  ({left_raw:,} raw) "
          f"— {left_pct:.1f}% ≈ {hm(left_raw / 7.5)} ≈ {left_raw/75:.1f} deathmatches")
    print(f"  At overload you will be:  Medal {mstr(ol_medal)}  Rank {ol_rank}  XP {ol_xp:,}")


# ──────────────────────────────────────────────────────────────
# MAIN LOGIC
# ──────────────────────────────────────────────────────────────

def main():
    weeks   = all_weeks()
    last_w  = weeks[-1]
    rows    = load()
    wn      = current_week()

    print(SEP)
    print(f"  CS2 XP TRACKER  │  Week {wn}/{weeks[-1]}  │  "
          f"{week_start(wn)} – {week_end(wn)}  │  Reset in {time_to_reset()}")
    print(SEP)

    # ── STEP 1: ask for starting state if week 7 has no data ──────────
    if START_WEEK not in rows:
        print(f"\n  No data found. Enter your state at the START of week {START_WEEK}:")
        medal = int(input("  Medal level (0–6): ").strip())
        rank  = int(input("  Rank (1–39): ").strip())
        xp    = int(input("  XP in rank (0–4999): ").strip())

        start_abs = to_abs(medal, rank, xp)
        projected = build_projection(start_abs, START_WEEK, weeks)
        rows.update(projected)
        save(rows)
        print(f"  Projection built from week {START_WEEK} to week {last_w}.\n")

    # ── STEP 2: choose which week to update ───────────────────────────
    raw_edit = input(f"\n  Update data for a different week? (Enter week number or press Enter for week {wn}): ").strip()
    edit_wn  = int(raw_edit) if raw_edit.isdigit() else wn

    if edit_wn not in rows:
        print(f"  Week {edit_wn} is not in the projection range ({weeks[0]}–{weeks[-1]}).")
        return

    print(f"\n  Projected state for week {edit_wn}:")
    show_week(rows[edit_wn], "PROJ")

    print(f"\n  Enter your ACTUAL rank/xp for week {edit_wn} (press Enter to skip):")
    raw_rank = input("  Rank (1–39): ").strip()
    raw_xp   = input("  XP in rank (0–4999): ").strip()

    if raw_rank or raw_xp:
        act_rank = int(raw_rank) if raw_rank else rows[edit_wn]["rank"]
        act_xp   = int(raw_xp)  if raw_xp   else rows[edit_wn]["xp"]

        cur_medal_guess = rows[edit_wn]["medal_lvl"]
        raw_medal = input(f"  Medal level [{cur_medal_guess}]: ").strip()
        act_medal = int(raw_medal) if raw_medal else cur_medal_guess

        act_abs  = to_abs(act_medal, act_rank, act_xp)
        proj_abs = to_abs(rows[edit_wn]["medal_lvl"], rows[edit_wn]["rank"], rows[edit_wn]["xp"])

        # Week baseline: previous week's abs XP + this week's mission XP
        if (edit_wn - 1) in rows:
            prev_abs = to_abs(rows[edit_wn-1]["medal_lvl"], rows[edit_wn-1]["rank"], rows[edit_wn-1]["xp"])
        else:
            prev_abs = proj_abs - NON_REDUCED_RAW - rows[edit_wn]["mission_xp"]
        week_baseline = prev_abs + rows[edit_wn]["mission_xp"]

        # proj_abs already includes any previously saved reduced XP for this week,
        # so extra_raw is genuinely new reduced XP gained since last update.
        # We accumulate it on top of whatever was already recorded.
        print()
        if act_abs >= proj_abs:
            extra_raw    = act_abs - proj_abs
            total_reduced = rows[edit_wn]["reduced_xp"] + extra_raw

            rows[edit_wn]["medal_lvl"]  = act_medal
            rows[edit_wn]["rank"]       = act_rank
            rows[edit_wn]["xp"]         = act_xp
            rows[edit_wn]["reduced_xp"] = total_reduced

            projected = build_projection(act_abs, edit_wn + 1, weeks)
            rows.update(projected)
            save(rows)

            print(f"  ✓ Week {edit_wn} updated — +{extra_raw:,} reduced XP this update  "
                  f"(total reduced this week: {total_reduced:,}).")
            print(f"  ✓ All weeks from {edit_wn + 1} re-projected from new baseline.")
        else:
            gained_raw   = max(0, act_abs - week_baseline)
            r4 = min(gained_raw, BASIC_4X * 4)
            r2 = min(max(gained_raw - BASIC_4X * 4, 0), BASIC_2X * 2)
            r1 = max(gained_raw - BASIC_4X * 4 - BASIC_2X * 2, 0)
            gained_basic = r4 // 4 + r2 // 2 + r1

            print(f"  Behind projection by {proj_abs - act_abs:,} XP — no changes saved.")
            print_progress(act_abs, gained_basic)

    # ── STEP 3: show full year projection table ────────────────────────
    print()
    print(SEP)
    print("  FULL YEAR PROJECTION")
    print(SEP)
    print(f"  {'Wk':>3}  {'Dates':<23}  {'Mission':>7}  "
          f"{'Medal':<14}  {'Rank':>4}  {'XP':>5}  {'Reduced':>7}")
    print(f"  {DIV}")

    for w in weeks:
        if w not in rows:
            continue
        r     = rows[w]
        m, rk, x = r["medal_lvl"], r["rank"], r["xp"]
        dates = f"{r['date_start']} – {r['date_end']}"
        tag   = " ◄" if w == wn else ""
        print(f"  {w:>3}  {dates:<23}  {r['mission_xp']:>7,}  "
              f"{mstr(m):<14}  {rk:>4}  {x:>5,}  {r['reduced_xp']:>7,}{tag}")

    # ── STEP 4: reduced XP needed if not reaching Pink ─────────────────
    final_row  = rows[last_w]
    final_abs  = to_abs(final_row["medal_lvl"], final_row["rank"], final_row["xp"])

    print(DIV)
    print(f"  Projected year-end:  Medal {mstr(final_row['medal_lvl'])}  "
          f"Rank {final_row['rank']}  XP {final_row['xp']:,}  "
          f"[abs {final_abs:,} / {PINK_TARGET:,}]")

    if final_abs < PINK_TARGET:
        gap         = PINK_TARGET - final_abs
        grind_weeks = [w for w in weeks if w != last_w and w >= wn]
        per_week    = gap / len(grind_weeks) if grind_weeks else gap
        # per_week is raw XP in reduced zone; to earn X reduced raw you play X/0.175 basic eq
        basic_eq    = per_week / 0.175
        print(f"  Gap to Pink:  {gap:,} XP over {len(grind_weeks)} weeks")
        print(f"  → Need {per_week:,.0f} raw reduced XP/week  "
              f"({basic_eq:,.0f} basic eq  ≈ {hm(basic_eq / 20)}/week) ≈ {basic_eq/200:.1f} deathmatches/week")
    else:
        print(f"  ✓ On track to reach Pink Medal!")

    print(SEP)


if __name__ == "__main__":
    main()
