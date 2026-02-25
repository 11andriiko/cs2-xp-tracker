import datetime
import os
import csv

def calculate_cs2_progress():
    # --- CONFIGURATION ---
    START_MEDAL_LV = 2      # 2 = Green
    TARGET_MEDAL_LV = 5     # 5 = Pink
    REDUCED_XP_LIMIT = 11167
    XP_PER_RANK = 5000
    XP_PER_MEDAL = 195000   # (40-1) * 5000 XP
    LOG_FILE = "cs2_xp_log.csv"
    MISSION_CYCLE = [600, 1050, 1050, 550, 1050, 1050, 600, 1050]
    TERMINAL_USED = 1       
    TERMINAL_MAX = 4        

    # --- CALENDAR LOGIC ---
    today = datetime.date.today()
    def get_prev_wednesday(dt): return dt - datetime.timedelta(days=(dt.weekday() - 2) % 7)
    
    current_week_start = get_prev_wednesday(today)
    prev_week_start = current_week_start - datetime.timedelta(days=7)
    next_reset = current_week_start + datetime.timedelta(days=7)
    first_wed_2026 = get_prev_wednesday(datetime.date(2026, 1, 7))
    week_num = ((current_week_start - first_wed_2026).days // 7) + 1
    
    all_wednesdays = [first_wed_2026 + datetime.timedelta(weeks=i) for i in range(53)]
    future_resets = [w for w in all_wednesdays if w >= next_reset and w.year == 2026]
    # Filter for divisor: weeks after the current one, excluding Week 52
    divisor_weeks = [w for w in future_resets if ((w - first_wed_2026).days // 7) + 1 < 52]
    num_future_resets = len(future_resets)
    num_divisor_weeks = len(divisor_weeks)
    total_weeks_in_year = len([w for w in all_wednesdays if w.year == 2026])

    # --- STATE LOADING ---
    last_rank, last_xp, mission_max, mission_earned = 0, 0, 0, 0
    current_medal_lv = START_MEDAL_LV
    prev_week_rank, prev_week_xp, prev_week_medal = None, None, None
    
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, mode='r') as f:
                rows = list(csv.DictReader(f))
                if rows:
                    last_entry = rows[-1]
                    last_rank = int(last_entry['rank'])
                    last_xp = int(last_entry['xp_in_rank'])
                    mission_max = int(last_entry['mission_max'])
                    current_medal_lv = int(last_entry.get('medal_lv', START_MEDAL_LV))
                    
                    for r in rows:
                        entry_date = datetime.date.fromisoformat(r['date'])
                        if entry_date < current_week_start:
                            prev_week_rank = int(r['rank'])
                            prev_week_xp = int(r['xp_in_rank'])
                            prev_week_medal = int(r.get('medal_lv', START_MEDAL_LV))
                        
                        if entry_date >= current_week_start:
                            mission_earned = int(r['mission_earned'])
        except: pass

    if prev_week_rank is None:
        prev_week_rank, prev_week_xp, prev_week_medal = last_rank, last_xp, current_medal_lv

    print(f"\n[ CALENDAR STATUS | WEEK {week_num} | NEXT RESET: {next_reset} ]")
    
    if mission_max == 0:
        mission_max = int(input(f">> Set MAX XP for mission (Predicted: {MISSION_CYCLE[(week_num-1)%8]}) XP: ") or MISSION_CYCLE[(week_num-1)%8])
    
    data_entered = False
    earned_now = 0
    if mission_earned < mission_max:
        input_mission = input(f">> Mission Progress ({mission_earned}/{mission_max}). Gained already: ")
        if input_mission:
            earned_now = int(input_mission)
            mission_earned = min(mission_max, mission_earned + earned_now)
            data_entered = True

    print(f">> Last Known: Rank {last_rank}, {last_xp} XP (Medal {current_medal_lv})")
    raw_rank = input(f">> Enter current Rank (Enter for {last_rank}): ")
    raw_xp = input(f">> Enter current XP (Enter for {last_xp}): ")
    
    if raw_xp:
        new_rank = int(raw_rank) if raw_rank else last_rank
        new_xp = int(raw_xp)
        if new_rank < last_rank and not (raw_rank == "" and new_xp < last_xp):
            current_medal_lv += 1
        last_rank, last_xp = new_rank, new_xp
        data_entered = True

    def get_abs_xp(m, r, x): return (m * 39 * XP_PER_RANK) + (r - 1) * XP_PER_RANK + x
    
    total_current_absolute = get_abs_xp(current_medal_lv, last_rank, last_xp)
    total_prev_week_absolute = get_abs_xp(prev_week_medal, prev_week_rank, prev_week_xp)
    total_week_xp = max(0, total_current_absolute - total_prev_week_absolute)

    if data_entered:
        file_exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, mode='a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists: 
                writer.writerow(['date', 'medal_lv', 'rank', 'xp_in_rank', 'mission_max', 'mission_earned'])
            writer.writerow([today.isoformat(), current_medal_lv, last_rank, last_xp, mission_max, mission_earned])
        print(f"\n[!] Data updated for {today.isoformat()}.")

    gameplay_xp = max(0, total_week_xp - mission_earned)
    
    m4_total = min(gameplay_xp, 4500)
    m4_basic, m4_bonus = m4_total / 4, (m4_total / 4) * 3
    m4_left = 4500 - m4_total
    m2_total = max(0, min(gameplay_xp, 7500) - 4500)
    m2_basic, m2_bonus = m2_total / 2, m2_total / 2
    m2_left = 3000 - m2_total
    m1_total = max(0, min(gameplay_xp, REDUCED_XP_LIMIT) - 7500)
    m1_left = 3667 - m1_total
    red_total = max(0, gameplay_xp - REDUCED_XP_LIMIT)
    red_basic = red_total / 0.175
    
    basic_sum = m4_basic + m2_basic + m1_total
    bonus_sum = m4_bonus + m2_bonus
    current_status = "0.175x" if gameplay_xp >= REDUCED_XP_LIMIT else ("1x" if gameplay_xp >= 7500 else ("2x" if gameplay_xp >= 4500 else "4x"))

    # --- LOGIC UPDATES ---
    total_mission_future = sum(MISSION_CYCLE[(week_num + i - 1) % 8] for i in range(num_future_resets + 1))
    
    # 1. Needed XP for pink medal: 5 * 39 * 5000
    pink_target_absolute = (TARGET_MEDAL_LV) * 39 * XP_PER_RANK
    
    # Projected state without grind
    projected_no_grind_gain = ((num_future_resets + 1) * REDUCED_XP_LIMIT) + total_mission_future
    f_medal, f_rank, f_xp = prev_week_medal, prev_week_rank, prev_week_xp + projected_no_grind_gain
    while f_xp >= XP_PER_RANK:
        f_xp -= XP_PER_RANK
        f_rank += 1
        if f_rank >= 40: f_rank = 1; f_medal += 1

    # 2. XP without grind calculation
    xp_without_grind = (f_medal * 39 * XP_PER_RANK) + ((f_rank - 1) * XP_PER_RANK) + f_xp
    
    # Recalculate debt and pace based on prev week absolute
    grind_debt = pink_target_absolute - xp_without_grind
    
    weekly_grind_needed = grind_debt / (num_divisor_weeks + 1) if num_divisor_weeks > 0 else grind_debt
    total_needed_this_week = REDUCED_XP_LIMIT + weekly_grind_needed + mission_earned
    diff_xp = total_week_xp - total_needed_this_week

    medal_names = {1: "Gray", 2: "Green", 3: "Blue", 4: "Purple", 5: "Pink", 6: "Red"}

    # --- OUTPUT ---
    print("\n" + "═"*75)
    print(f"                 2026 PINK MEDAL ANALYTICS")
    print("═"*75)
    print(f"WEEK {week_num}/{total_weeks_in_year} TOTAL:      {basic_sum:,.0f} BASIC + {bonus_sum:,.0f} BONUS + {red_total:,} REDUCED + {mission_earned:,} MISSION = {gameplay_xp + mission_earned:,} XP")
    print(f"CURRENT XP STATUS:    {current_status}")
    print(f"WEEKLY PACE TRACKER:  {total_week_xp:,.0f}/{total_needed_this_week:,.0f} ({'+' if diff_xp >=0 else ''}{diff_xp:,.0f} XP)")
    print("-" * 75)
    print(f"MISSION STATUS:  {mission_earned:,} XP (LEFT: {max(0, mission_max - mission_earned):,} XP)")
    print(f"BONUS 4x :       {m4_total:,.0f} XP (LEFT: {m4_left:,.0f} XP)")
    print(f"BONUS 2x :       {m2_total:,.0f} XP (LEFT: {m2_left:,.0f} XP)")
    print(f"BASIC 1x :       {m1_total:,.0f} XP (LEFT: {m1_left:,.0f} XP)")
    print(f"REDUCED 0.175x:  {red_total:,.0f} XP (BASIC: {red_basic:,.0f} XP)")
    print("-" * 75)
    print(f"TO NEXT RANK:    {max(0, XP_PER_RANK - last_xp):,} XP")
    
    # Calculate XP and levels needed for the very next medal color
    next_medal_target_absolute = (current_medal_lv + 1) * 39 * XP_PER_RANK
    xp_to_next_medal = next_medal_target_absolute - total_current_absolute
    print(f"TO NEXT MEDAL:   {xp_to_next_medal:,.0f} XP ({xp_to_next_medal // XP_PER_RANK} LVL+)")
    
    xp_to_pink = pink_target_absolute - total_current_absolute
    print(f"TO PINK MEDAL:   {xp_to_pink:,.0f} XP ({xp_to_pink // XP_PER_RANK} LVL+)")
    print("-" * 75)
    print(f"WEEKLY QUOTA (PACE):      {REDUCED_XP_LIMIT:,} XP + {int(weekly_grind_needed):,} GRIND = {int(total_needed_this_week):,} XP")
    print("-" * 75)
    print(f"PROJECTED END OF 2026 STATUS (NO GRIND):")
    print(f"FINAL MEDAL: {medal_names.get(f_medal, 'Unknown')} | FINAL RANK: {f_rank} ({f_xp:,} XP)")
    print("-" * 75)
    print(f"WEEKS LEFT: {num_future_resets}")
    print("═"*75)

if __name__ == "__main__":
    calculate_cs2_progress()
