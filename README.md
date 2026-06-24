# CS2 XP Tracker

A terminal-based tracker for weekly XP progress in Counter-Strike 2. It logs
your Medal / Rank / XP each week, works out how much "Basic XP" and "Reduced
XP" you've earned against the game's diminishing-returns XP curve, projects
when you'll next rank up or hit your weekly mission cap, and estimates how
much Deathmatch or Competitive playtime that translates to.

Data is stored locally in a single JSON file next to the program — no
account, no internet connection, and no external service involved.

---

## Table of contents

- [Features](#features)
- [Quick start (running from source)](#quick-start-running-from-source)
- [Command reference](#command-reference)
- [Building a standalone .exe](#building-a-standalone-exe)
- [Building a real Windows installer](#building-a-real-windows-installer)
- [Installing for end users (no Python required)](#installing-for-end-users-no-python-required)
- [Downloading via PowerShell](#downloading-via-powershell)
- [Moving this repo to a different GitHub account](#moving-this-repo-to-a-different-github-account)
- [Project structure](#project-structure)
- [Data file format](#data-file-format)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- **Weekly status view** — current Medal/Rank/XP, current XP stage (4x →
  2x → 1x → 0.175x overload), progress bars for stage XP, total XP, and
  weekly mission XP.
- **Rank-up / weekly-drop projection** — how much Basic XP you still need,
  shown both with and without your remaining weekly mission XP factored in,
  plus an estimated number of Deathmatch or Competitive games and minutes.
- **Overload math** — once you've used up the week's 4x/2x/1x stages,
  everything after is multiplied by 0.175x; the tool tracks this
  automatically and reflects it in every estimate.
- **Historical + projected tables** — view every recorded week, a single
  week, or a range (`3-7`), with an optional projection mode that estimates
  future weeks if you keep earning XP at a similar rate.
- **Self-building** — typing `build` inside the running tool compiles
  itself into a single-file Windows `.exe` using PyInstaller, with all
  build artifacts cleaned up automatically afterward.
- **Zero external dependencies for data** — everything is kept in one
  human-readable `cs2xp.json` file you fully own.

---

## Quick start (running from source)

Requirements: **Python 3.10+** (uses `datetime.UTC`, added in 3.11 — if
you're on 3.10 see [Troubleshooting](#troubleshooting)).

```powershell
# 1. Clone the repository
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

# 2. (Recommended) create a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run it
python cs2xp.py
```

You'll land in an interactive prompt:

```
[cs2xp] >
```

Type `h` for help at any time.

---

## Command reference

| Command | Aliases | What it does |
|---|---|---|
| `status` | `s`, `stat` | Show status for the current week. Add `-week N` / `-w N` to view a specific week. |
| `update` | `u`, `upd` | Update this week's numbers. Default mode asks for Medal, Rank, XP, and Mission XP. Modes: `-full`/`-f` (all fields, can also pick a different week first), `-medal`/`-med`, `-rank`/`-r`, `-xp`, `-mission`/`-mis` (only that one field). |
| `table` | `t` | Show a table of recorded weeks. `-existing`/`-e` (default) shows only real data; `-projected`/`-p [amount]` shows a future projection (optionally with a custom weekly XP rate); `-full`/`-f` shows both. Add a week range like `1-10` to filter. |
| `delete` | `d` | Delete one week or a range, e.g. `d 5` or `d 3-7`. |
| `build` | `b` | Compile this script into `cs2xp.exe` via PyInstaller (not available once already running as a compiled `.exe`). |
| `help` | `h` | Show in-app help text. |
| `exit` | `quit`, `stop`, `e`, `q` | Close the session. |

**Examples:**

```text
[cs2xp] > s
[cs2xp] > u -rank
[cs2xp] > t 1-12 -f
[cs2xp] > d 9
[cs2xp] > b
```

---

## Building a standalone .exe

You don't need any extra steps beyond what's already in the script — this
is built in.

1. Run the script normally: `python cs2xp.py`
2. At the prompt, type:
   ```
   build
   ```
   or the shortcut `b`.
3. The script will:
   - Install PyInstaller automatically if it isn't already installed.
   - Run PyInstaller with `--onefile` in a temporary directory (so no
     `build/` or `.spec` clutter is left in your project folder).
   - Produce `cs2xp.exe` directly inside your project folder.

You can also do this manually, outside the script, with the same effect:

```powershell
pip install pyinstaller
pyinstaller --onefile --noconfirm --clean cs2xp.py
# the .exe will be inside the generated "dist" folder
```

The in-app `build` command is just a convenience wrapper around the same
PyInstaller call, with automatic cleanup.

---

## Building a real Windows installer

A raw `.exe` is **not** the same thing as an installer — it doesn't create
a Start Menu entry, doesn't appear in "Add or Remove Programs," and doesn't
offer an uninstaller. To get an actual installer experience for end users,
this repo includes `cs2xp_installer.iss`, a script for **Inno Setup** (a
free, widely-used Windows installer compiler).

**Steps:**

1. **Build `cs2xp.exe` first** (see previous section).
2. **Install Inno Setup** from <https://jrsoftware.org/isinfo.php> (free).
3. Place `cs2xp.exe` in the **same folder** as `cs2xp_installer.iss`.
4. Open `cs2xp_installer.iss` in the Inno Setup Compiler.
5. *(Optional but recommended)* Open the file and edit:
   - `MyAppPublisher` → your name or organization
   - `AppId` → generate your own GUID at
     <https://www.guidgenerator.com/> and paste it in (keeps future
     updates recognized as the same app rather than a duplicate install)
6. Click **Compile** (or right-click the `.iss` file in Explorer and
   choose **Compile**).
7. Inno Setup produces `Output\CS2XPTracker-Setup.exe`.

**That file — `CS2XPTracker-Setup.exe` — is the installer you distribute.**
Running it on a user's machine will:

- Install the app to `%LocalAppData%\Programs\CS2 XP Tracker` (no admin
  rights required)
- Add a Start Menu shortcut
- Optionally add a Desktop shortcut
- Register a proper uninstaller in Windows Settings → Apps

---

## Installing for end users (no Python required)

Once you've built `CS2XPTracker-Setup.exe` (previous section) and attached
it to a [GitHub Release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository),
a user with **no Python, no Git, no IDE** can:

1. Go to your repo's **Releases** page.
2. Download `CS2XPTracker-Setup.exe`.
3. Double-click it, click through the install wizard.
4. Launch "CS2 XP Tracker" from the Start Menu.

Windows SmartScreen will likely warn that the publisher is unrecognized the
first time, since the `.exe` isn't code-signed — this is expected for
small/independent tools and is unrelated to whether the program is safe.
Users can proceed via **More info → Run anyway**. Code-signing certificates
exist but cost money and aren't necessary for this to work.

---

## Downloading via PowerShell

If you'd rather let users grab a file with a command instead of clicking
through the GitHub UI (e.g. for a pinned release URL), PowerShell's
`Invoke-WebRequest` works directly against a GitHub Release asset:

```powershell
Invoke-WebRequest `
  -Uri "https://github.com/<your-username>/<your-repo>/releases/latest/download/CS2XPTracker-Setup.exe" `
  -OutFile "$env:USERPROFILE\Downloads\CS2XPTracker-Setup.exe"

# then run it:
Start-Process "$env:USERPROFILE\Downloads\CS2XPTracker-Setup.exe"
```

The `releases/latest/download/<filename>` URL pattern always resolves to
the newest published release with an asset of that exact name, so this
command keeps working across future versions without editing the link —
as long as you keep naming the asset `CS2XPTracker-Setup.exe` in each
release.

If someone instead just wants the raw source (e.g. to run with Python
themselves) without installing Git, they can grab a zip of the repo the
same way:

```powershell
Invoke-WebRequest `
  -Uri "https://github.com/<your-username>/<your-repo>/archive/refs/heads/main.zip" `
  -OutFile "$env:USERPROFILE\Downloads\cs2xp-source.zip"

Expand-Archive "$env:USERPROFILE\Downloads\cs2xp-source.zip" -DestinationPath "$env:USERPROFILE\Downloads\cs2xp-source"
```

---

## Moving this repo to a different GitHub account

To push this project to a **different** GitHub account than the one it's
currently connected to in VS Code:

1. **Create a new empty repository** on the target GitHub account (via
   the GitHub website — don't initialize it with a README, so it stays
   empty and avoids merge conflicts on first push).
2. In your VS Code terminal, check what remote you currently have:
   ```powershell
   git remote -v
   ```
3. Point `origin` at the new repo instead of removing/re-adding it:
   ```powershell
   git remote set-url origin https://github.com/<new-account>/<new-repo>.git
   ```
4. Push everything:
   ```powershell
   git push -u origin main
   ```
   (use `master` instead of `main` if that's your default branch name —
   check with `git branch`)
5. If VS Code prompts for GitHub sign-in and it's currently authenticated
   as your *old* account, sign out via the Accounts icon in the bottom-left
   of VS Code, then sign in as the new account when prompted, or use a
   [Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
   for that specific account if you need both accounts usable
   side-by-side.

From that point on, `git push` from VS Code goes to the new account's repo,
and the PowerShell download commands above will work once you substitute
in `<new-account>/<new-repo>`.

---

## Project structure

```
.
├── cs2xp.py                 # Main script — the entire application
├── requirements.txt         # Python dependencies
├── cs2xp_installer.iss      # Inno Setup script — builds the Windows installer
├── LICENSE
├── .gitignore
└── README.md
```

Generated at runtime (not committed to git):

```
cs2xp.json      # Your personal weekly XP data — created on first run
cs2xp.exe       # Created by the in-app "build" command
Output/         # Created by Inno Setup when compiling the installer
```

---

## Data file format

`cs2xp.json` is a flat dictionary keyed by week number (as a string), e.g.:

```json
{
  "1": {
    "abs_xp": 42000,
    "medal": 0,
    "rank": 9,
    "xp": 2000,
    "basic_xp": 6292,
    "reduced_xp": 1100,
    "mission_actual": 600,
    "mission_max": 600,
    "date_start": "2026-01-07",
    "date_end": "2026-01-13"
  }
}
```

It's a plain text file — back it up by copying it, or move it between
machines by copying it next to the script/`.exe` on the new machine.

---

## Troubleshooting

**"ModuleNotFoundError: No module named 'rich'"**
Run `pip install -r requirements.txt` in the same Python environment
you're using to run the script.

**Script errors on `datetime.UTC`**
That attribute was added in Python 3.11. Either upgrade Python, or replace
`datetime.UTC` with `datetime.timezone.utc` in `week_now()` if you need to
support 3.10.

**`build` command fails / PyInstaller errors**
Make sure you're running `python cs2xp.py` from source (not from an already
-built `.exe`) — the build command is disabled when running the compiled
version. Check that you have write permissions in the project folder.

**Windows SmartScreen blocks the installer or the .exe**
This happens to all unsigned executables, not just this one. Click
**More info → Run anyway**. This is a Windows publisher-verification
prompt, not an antivirus detection.

**PowerShell blocks running the downloaded installer**
If `Start-Process` or double-clicking does nothing, the file may be
flagged as downloaded from the internet. Right-click the `.exe` →
Properties → check **Unblock** → OK, then try again.

---

## License

MIT — see [LICENSE](LICENSE).
