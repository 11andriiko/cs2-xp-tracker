# CS2 XP Tracker

A fast, terminal-based CLI for tracking **weekly XP progression in Counter-Strike 2** — including stage breakdowns, rank projections, and realistic playtime estimates.

No accounts. No APIs. Just your data.

---

## 🚀 What it does

CS2 XP isn’t linear — it follows a staged system (4× → 2× → 1× → 0.175×).
This tool tracks your progress **accurately**, week by week, and answers:

* How much XP did I *really* earn?
* What stage am I in right now?
* How much do I need for next rank / weekly drop?
* How much do I need to play (DM / Competitive)?
* What happens if I keep this pace?

---

## ✨ Core Features

### 📊 Smart weekly tracking

* Stores Medal / Rank / XP per week
* Automatically computes:

  * **Basic XP**
  * **Reduced XP (overload)**
  * Total gained XP

### ⚡ Accurate XP math

* Fully models CS2 XP stages:

  * 4× → 2× → 1× → 0.175×
* Handles edge cases (4× stage cap rounding)
* Correct overload calculations

### 🔁 Cascade-safe updates

* Updating past weeks:

  * Automatically fixes all future weeks
  * Ensures **monotonic XP progression**
  * Recalculates derived values (`basic_xp`, `reduced_xp`)
* Includes **full cascade diff preview before saving**

### 📈 Status & projections

* Current week breakdown:

  * Stage progress
  * XP progress bars
  * Mission progress
* Rank-up / weekly-drop estimates
* Playtime estimation:

  * Deathmatch
  * Competitive

### 🔮 Year projection

* Simulate future progress:

  * Set mission completion level
  * Set weekly XP target
* See full year outcome instantly

### 🧾 Local & transparent

* Data stored in:

  ```
  cs2xp_data.json
  ```
* Human-readable
* Fully portable

---

## 🖥️ Quick Start

### Requirements

* Python **3.10+** (3.11 recommended)

### Run from source

```bash
git clone https://github.com/11andriiko/cs2-xp-tracker.git
cd cs2-xp-tracker

python -m venv .venv
.venv\Scripts\activate   # Windows

pip install -r requirements.txt
python cs2xp.py
```

You’ll see:

```
[cs2xp] >
```

---

## ⌨️ Commands

### Status

```
status | s | stat
```

Show current progress

```
status -week 5
```

---

### Update

```
update | u
```

Modes:

```
u                # full (week + all fields)
u -med           # medal + rank + xp
u -r             # rank + xp
u -xp            # xp only
u -mis           # mission only
```

✔ Includes:

* validation vs previous week
* cascade preview
* safe apply

---

### Table

```
table | t
```

Show all recorded weeks

---

### Delete

```
delete 5
delete 3-7
```

---

### Projection

```
projection | p
```

Examples:

```
p
p -mission 3 -xp overload
p -mission 1 -xp 4000
```

---

### Help

```
help
help -commands
```

---

### Exit

```
exit | q
```

---

## 🧠 How XP works (simplified)

Each week:

| Stage    | Basic XP | Multiplier |
| -------- | -------- | ---------- |
| 4×       | 1167     | 4×         |
| 2×       | 1500     | 2×         |
| 1×       | 3500     | 1×         |
| Overload | ∞        | 0.175×     |

* Mission XP is **added separately**
* After 6167 basic XP → overload begins

This tool handles all of that automatically.

---

## 📁 Data Format

Example:

```json
{
  "5": {
    "abs_xp": 585194,
    "medal": 3,
    "rank": 1,
    "xp": 194,
    "basic_xp": 3200,
    "reduced_xp": 0,
    "mission_actual": 600,
    "mission_max": 1050
  }
}
```

---

## 🔒 Design Principles

* **Deterministic** — same input → same result
* **No hidden state** — everything in JSON
* **Correct over convenient** — XP math is exact
* **Safe editing** — cascade preview before applying

---

## ⚠️ Notes

* XP **cannot decrease across weeks**
* Editing past weeks will affect future weeks
* Large reduced XP = heavy overload play

---

## 🛣️ Roadmap (optional ideas)

* Diff highlighting in tables
* Export to CSV
* Graph view
* Configurable XP sources

---

## 📄 License

MIT
