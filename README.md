# Vision Assistance App

Vision Assistance App is a Windows desktop accessibility tool for visually impaired users.

It listens for global hotkeys, captures the current screen, asks Gemini for a description, reads a summary out loud, and lets users navigate details with keyboard shortcuts.

## Download for Windows

[![Download Windows App](https://img.shields.io/badge/Download-Windows%20App-2EA44F?style=for-the-badge)](https://github.com/chandrachood/windows-desktop-vision-assistant/releases/latest/download/VisionAssistanceApp-windows.zip)
[![Direct EXE](https://img.shields.io/badge/Direct-EXE-0969DA?style=for-the-badge)](https://github.com/chandrachood/windows-desktop-vision-assistant/releases/latest/download/VisionAssistanceApp.exe)

End-user quick start:

1. Click the green `Download Windows App` button above.
2. Extract the zip and run `VisionAssistanceApp.exe`.
3. On first run, enter your Gemini API key when prompted.
4. Press `Ctrl+M` to describe the current screen.
5. To change API key later, press `Ctrl+Alt+K`.

Notes:
- `config.json` is auto-created on first run.
- API key is saved encrypted in local config.
- If the direct download link says not found, publish the first GitHub release, then retry.

## Key Features

- Global hotkeys for capture, detail navigation, and exit
- Summary-first narration for faster understanding
- Step-through detail reading (`Detail 1 of N`, `Detail 2 of N`, ...)
- Audible periodic ticks while AI capture/analysis is running
- Interactive voice follow-up on the current screen (`Ctrl+N` start, `Ctrl+N` send)
- Instant narration interruption (`Ctrl+Shift+S`) and action preemption
- Cancel in-progress capture/follow-up task (`Ctrl+Shift+X`)
- Encrypted local storage for Gemini API key
- First-run API key prompt (console or dialog) with automatic encryption
- Single-instance protection to avoid duplicate hotkey conflicts
- Multi-backend speech fallback for better reliability on Windows

## Hotkeys

- `Ctrl+M`: Capture screen and read summary
- `Ctrl+N`: Start follow-up recording, then press again to submit immediately
- `Ctrl+Shift+S`: Stop current speech immediately
- `Ctrl+Shift+X`: Cancel current capture/follow-up task
- `Ctrl+Alt+K`: Set or update Gemini API key
- `Ctrl+Right` or `Ctrl+Down`: Next detail
- `Ctrl+Left` or `Ctrl+Up`: Previous detail
- `Ctrl+Shift+Q`: Exit app
- `Ctrl+C` (terminal): Graceful stop

Action hotkeys (`Ctrl+M`, `Ctrl+N`, detail navigation) now interrupt current narration first, so users can move to the next step without waiting for speech to finish.

## Requirements

For end users (EXE mode):

- Windows 10/11
- Gemini API key

For developers (source mode):

- Windows 10/11
- Python 3.10+
- Gemini API key

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Do not use real credentials in repository files.

1. Copy config template:

```bash
copy config.example.json config.json
```

2. Option A: run the app and enter API key when prompted.
3. Option B: add your Gemini key manually in `config.json` under `api_key`.
4. On first successful use, the app encrypts the key and clears plaintext automatically.

Runtime file locations:
- Source mode (`python main.py`): files are stored in the project folder.
- EXE mode (`VisionAssistanceApp.exe`):
  - `config.json`: auto-created in EXE folder (when writable), otherwise `%APPDATA%\VisionAssistanceApp\config.json`
  - lock file: `%APPDATA%\VisionAssistanceApp\.vision_assistant.lock`
  - `app.log`: same folder as the EXE (`VisionAssistanceApp.exe`) when writable
  - fallback log copy: `%APPDATA%\VisionAssistanceApp\app.log`

## Run

```bash
python main.py
```

## Project Docs

- `howitworks.md`: technical architecture and runtime behavior
- `GITHUB_SETUP.md`: repository publishing and GitHub settings checklist
- `CONTRIBUTING.md`: contribution workflow
- `CODE_OF_CONDUCT.md`: community standards
- `SECURITY.md`: vulnerability disclosure and security practices
- `SUPPORT.md`: support and reporting channels
- `CHANGELOG.md`: release history and user-facing changes
- `LICENSE`: project license (MIT)

## Open-Source Safety

Before publishing:

- keep `config.json` empty or local-only
- remove/clear `app.log`
- do not publish `venv/` or runtime lock files
- use `config.example.json` for examples

`.gitignore` is configured for these local artifacts.

## Packaging as Windows EXE

Use these exact steps in PowerShell from project root:

1. Create virtual environment (one-time):

```powershell
python -m venv venv
```

2. Activate virtual environment:

```powershell
.\venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

4. Optional local validation before build:

```powershell
python -m py_compile main.py
```

5. Build EXE (console mode):

```powershell
.\build_exe.ps1
```

6. Or build EXE (windowed mode, no console window):

```powershell
.\build_exe.ps1 -Windowed
```

7. Verify build output:

- `dist\VisionAssistanceApp.exe`
- `dist\config.example.json`

8. Test the generated EXE locally:

```powershell
.\dist\VisionAssistanceApp.exe
```

9. Optional distribution zip:

```powershell
Compress-Archive -Path .\dist\VisionAssistanceApp.exe,.\dist\config.example.json -DestinationPath .\dist\VisionAssistanceApp-windows.zip -Force
```

10. For end users:

- Share the EXE (or zip) on Windows 10/11.
- On first run, set API key when prompted or with `Ctrl+Alt+K`.
- Runtime config/log files are stored under `%APPDATA%\VisionAssistanceApp`.

## Limitations

- Internet is required for Gemini description calls.
- Speech behavior can vary by Windows audio routing settings.
- Current implementation is Windows-first.
