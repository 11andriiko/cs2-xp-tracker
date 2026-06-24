; ════════════════════════════════════════════════════════════════
;  CS2 XP Tracker — Inno Setup installer script
; ════════════════════════════════════════════════════════════════
;  WHAT THIS FILE IS
;  This is NOT a Python file and you do not run it with Python.
;  It is a script for "Inno Setup", a free Windows tool that compiles
;  a normal .exe into a proper Setup.exe (the kind that puts a shortcut
;  in the Start Menu and an entry in "Add or Remove Programs").
;
;  HOW TO USE IT (full step-by-step is in README.md)
;  1. Build cs2xp.exe first (run cs2xp.py and type "build", or run
;     PyInstaller manually).
;  2. Put cs2xp.exe in the SAME folder as this .iss file.
;  3. Install Inno Setup from https://jrsoftware.org/isinfo.php
;  4. Open this file in the Inno Setup Compiler and click Compile
;     (or right-click it in Explorer -> "Compile").
;  5. The finished installer appears in an "Output" folder as
;     CS2XPTracker-Setup.exe — that is the file you give to users.
; ════════════════════════════════════════════════════════════════

#define MyAppName "CS2 XP Tracker"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "11andriiko"
#define MyAppExeName "cs2xp.exe"

[Setup]
; A fixed GUID that uniquely identifies THIS application across versions.
; Generate your own at https://www.guidgenerator.com/ and replace it below
; (keep the curly braces). Do not reuse this exact GUID in a real release.
AppId={{29dc35198c0d44d394cc0991533d1955}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Output installer name and location (relative to this .iss file)
OutputDir=Output
OutputBaseFilename=CS2XPTracker-Setup
Compression=lzma2
SolidCompression=yes
; Standard user-level install location, no admin rights required
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Use your own .ico file here if you have one; comment out the line
; below if you don't have an icon yet.
;SetupIconFile=cs2xp.ico
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; The compiled exe produced by cs2xp.py's "build" command (PyInstaller).
; This MUST sit next to this .iss file when you compile the installer.
Source: "cs2xp.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch the app right after install finishes.
; Filename points at cmd.exe so a console window stays open for the
; interactive CLI instead of flashing closed.
Filename: "{cmd}"; Parameters: "/K ""{app}\{#MyAppExeName}"""; \
    Description: "Launch {#MyAppName} now"; Flags: postinstall skipifsilent nowait
