# How It Works

This document explains how the Vision Assistance App works internally and what is required to run and open-source it safely.

## 1. Purpose

The app helps visually impaired users understand on-screen content.

It does this by:
- listening for global hotkeys,
- taking a screenshot of the current screen,
- sending the image to Google Gemini for description,
- speaking a short summary first,
- then letting the user navigate detailed chunks using keyboard shortcuts.

## 2. Runtime Flow

### Startup

When `main.py` starts, it:
1. acquires a single-instance lock (`.vision_assistant.lock`) so only one app instance can run,
2. loads `config.json`,
3. decrypts the API key if encrypted credentials exist,
4. if key is missing, prompts user for API key (console or GUI dialog),
5. encrypts and stores the entered key in `config.json`,
6. initializes speech configuration,
7. registers global hotkeys,
8. announces usage instructions.

### Capture and Summary (`Ctrl+M`)

When the user presses `Ctrl+M`:
1. a capture lock prevents concurrent capture requests,
2. the app takes a screenshot (`pyautogui`),
3. image bytes are sent to Gemini (`google-genai`),
4. periodic audible ticks indicate AI work is still in progress,
5. the response text is normalized for speech,
6. a summary is built from the first one or two sentences,
7. summary speech is played aloud,
8. detail chunks are stored for navigation,
9. navigation instructions are spoken.

### Voice Follow-Up (`Ctrl+N`)

When the user presses `Ctrl+N`:
1. app prompts user to speak after a beep,
2. app enters recording mode with an audible start cue,
3. user can press `Ctrl+N` again to stop recording and submit immediately,
4. if not manually submitted, recording auto-stops after max duration,
5. app captures current screen,
6. screenshot + spoken question are sent to Gemini,
7. response is read aloud.

### API Key Update (`Ctrl+Alt+K`)

When the user presses `Ctrl+Alt+K`:
1. the app opens the same secure API key prompt flow,
2. user enters a new key,
3. key is encrypted and stored in `config.json`,
4. in-memory key is updated immediately (no restart required).

### Detail Navigation

After summary is available:
- `Ctrl+Right` or `Ctrl+Down`: next detail chunk
- `Ctrl+Left` or `Ctrl+Up`: previous detail chunk

The app speaks:
- `Detail X of Y ...`

### Speech Interrupt and Preemption

- `Ctrl+Shift+S`: immediately stops current narration.
- `Ctrl+Shift+X`: cancels current long task (capture or follow-up), including active mic transcription and in-flight model request.
- Pressing action hotkeys (`Ctrl+M`, `Ctrl+N`, detail navigation) preempts current speech first.
- This lets users skip ongoing narration and move to the next question or step without waiting for full speech completion.

### Exit

The app stops by:
- `Ctrl+Shift+Q` hotkey, or
- `Ctrl+C` in terminal.

Hotkeys are unregistered and the process exits.

## 3. Speech Pipeline

Speech output is serialized with a lock so utterances do not overlap.

Backends are tried in this order:
1. wave-file synthesis + playback (`System.Speech` -> `.wav` -> `winsound`)
2. `cscript` SAPI voice
3. PowerShell `System.Speech`
4. `pyttsx3` fallback

This layered approach increases reliability across Windows configurations.

## 4. Configuration and API Key Security

Configuration file: `config.json`

Fields:
- `api_key`: plaintext key (used only for first-run encryption)
- `encrypted_key`: encrypted API key
- `encryption_key`: Fernet key used to decrypt `encrypted_key`

Behavior:
- If `api_key` is present and encrypted fields are empty, app encrypts it and clears plaintext.
- If encrypted fields are present, app decrypts in memory at startup.

Important:
- `config.json` is local and should never be committed.
- `config.example.json` is the safe template for the repo.

Runtime location:
- source mode: project directory
- packaged EXE mode: `%APPDATA%\VisionAssistanceApp`

Log location in EXE mode:
- primary: same folder as `VisionAssistanceApp.exe`
- fallback: `%APPDATA%\VisionAssistanceApp\app.log` if EXE folder is not writable

## 5. Logging

Runtime logs are written to `app.log` and include:
- hotkey events,
- API errors,
- screenshot failures,
- speech backend events.

Do not publish `app.log` because it may contain sensitive screen descriptions.

## 6. Concurrency Model

The app uses threads for:
- speech dispatch,
- hotkey-triggered capture processing,
- detail navigation speech.

Safety controls:
- speech lock (prevents overlapping TTS execution),
- capture lock (prevents duplicate `Ctrl+M` runs),
- single-instance lock (prevents duplicate app processes and hotkey conflicts).

## 7. Project Files

Core files:
- `main.py`: app runtime
- `requirements.txt`: Python dependencies
- `config.example.json`: public-safe config template
- `README.md`: user guide
- `howitworks.md`: this technical guide

Open-source governance files:
- `LICENSE`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `.gitignore`

## 8. Open-Source Readiness Checklist

Before publishing:
1. ensure `config.json` has no real credentials,
2. clear `app.log`,
3. keep `venv/` and runtime artifacts ignored by `.gitignore`,
4. include a license (`LICENSE`),
5. include contribution and conduct policies,
6. include a security disclosure path,
7. verify install instructions from a clean machine.

## 9. Known Constraints

- Windows-first implementation (hotkeys and speech stack are Windows-oriented).
- Internet connection is required for Gemini image description.
- Global hotkey registration may require running in a standard desktop session.

## 10. Recommended Open-Source Publishing Steps

1. Create a new Git repository.
2. Copy this project without local virtual environment and logs.
3. Commit files including docs and governance files.
4. Push to GitHub (or equivalent).
5. Add repository topics (accessibility, screen-reader, genai, python, windows).
6. Enable issue tracker and pull requests.
7. Add release notes for the first public version.

## 11. Packaging Notes

Use the repository build script:

```powershell
.\build_exe.ps1
```

This generates:
- `dist\VisionAssistanceApp.exe`
- `dist\config.example.json`

For a no-console executable:

```powershell
.\build_exe.ps1 -Windowed
```
