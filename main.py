"""
Vision Assistance Application
----------------------------

This script implements a simple desktop assistant aimed at supporting
people with visual impairments. It registers a global hot‑key (CTRL+M)
to capture the current screen, sends the screenshot to Google’s
Gemini model via the `google‑genai` SDK and speaks the model’s
response aloud using the built‑in text‑to‑speech engine. A second
hot‑key (CTRL+SHIFT+Q) cleanly shuts down the application. The
application reads its API key from a configuration file and
automatically encrypts it on first use to avoid accidental misuse.

Dependencies:
    - google‑genai (for calling Gemini models)
    - cryptography (for symmetric encryption of API keys)
    - keyboard (for global hot‑key registration)
    - pyautogui (for taking screenshots)
    - pyttsx3 (for speech synthesis)

All of these packages must be installed in your Python environment
before running this script. See requirements.txt for details.

Usage:
    python main.py

When packaged into a Windows executable via a tool like PyInstaller
(`pyinstaller --onefile main.py`), launching the executable will show
instructions and immediately register the hot‑keys. Press CTRL+M to
request a screen description or CTRL+SHIFT+Q to exit.

Copyright 2026, Vision Assistance Project
"""

import io
import json
import logging
import getpass
import msvcrt
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
import winsound
from pathlib import Path

# External libraries – these imports will fail if the appropriate
# dependencies are not installed. See requirements.txt for details.
try:
    import keyboard  # type: ignore
    import pyautogui  # type: ignore
    import pyttsx3  # type: ignore
    from cryptography.fernet import Fernet  # type: ignore
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
except ImportError as exc:
    missing = exc.name if hasattr(exc, 'name') else str(exc)
    print(f"Error: Missing dependency '{missing}'. Please install all "
          f"requirements listed in requirements.txt before running this script.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration handling
#
# The configuration file stores the encrypted API key alongside the
# encryption key itself. On the first run, users can place their
# plaintext API key in the "api_key" field. The program will
# automatically encrypt it and clear the plaintext value for safety.
#
# In source mode we keep files next to main.py.
# In bundled (.exe) mode we store runtime files under %APPDATA%
# so data persists across launches and is writable without admin rights.


def get_runtime_dir() -> Path:
    """Return the writable directory for config, logs, and lock files."""
    if getattr(sys, "frozen", False):
        appdata_root = Path(
            os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        )
        runtime_dir = appdata_root / "VisionAssistanceApp"
    else:
        runtime_dir = Path(__file__).resolve().parent
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def get_executable_dir() -> Path:
    """Return executable directory in EXE mode, script directory otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_directory_writable(directory: Path) -> bool:
    """Return True if directory is writable by current user."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".vision_assistant_write_probe"
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def get_config_path(runtime_dir: Path, executable_dir: Path) -> Path:
    """Pick config location: EXE folder when writable, else runtime dir."""
    if getattr(sys, "frozen", False) and is_directory_writable(executable_dir):
        return executable_dir / "config.json"
    return runtime_dir / "config.json"


RUNTIME_DIR = get_runtime_dir()
EXECUTABLE_DIR = get_executable_dir()
CONFIG_PATH = get_config_path(RUNTIME_DIR, EXECUTABLE_DIR)
LOG_PATH = EXECUTABLE_DIR / "app.log"
FALLBACK_LOG_PATH = RUNTIME_DIR / "app.log"
LOCK_PATH = RUNTIME_DIR / ".vision_assistant.lock"


class SingleInstanceLock:
    """Prevent multiple app instances from running at the same time."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._handle = None

    def acquire(self) -> bool:
        self._handle = open(self.lock_path, "a+b")
        self._handle.seek(0)
        try:
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            if not self._handle.read(1):
                self._handle.seek(0)
                self._handle.write(b"1")
                self._handle.flush()
            return True
        except OSError:
            self._handle.close()
            self._handle = None
            return False

    def release(self) -> None:
        if not self._handle:
            return
        try:
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        self._handle.close()
        self._handle = None


def load_config() -> dict:
    """Load configuration from disk. If the file does not exist, create it
    with default values.

    Returns
    -------
    dict
        The configuration dictionary.
    """
    if not CONFIG_PATH.exists():
        default_conf = {
            "api_key": "",
            "encrypted_key": "",
            "encryption_key": ""
        }
        CONFIG_PATH.write_text(json.dumps(default_conf, indent=4))
        return default_conf
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to read config file: {e}")
        return {}


def save_config(conf: dict) -> None:
    """Persist the configuration back to disk."""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(conf, f, indent=4)


def configure_logging() -> Path:
    """Configure file logging, preferring executable directory."""
    handlers: list[logging.Handler] = []
    chosen_log_path = LOG_PATH
    try:
        handlers.append(logging.FileHandler(LOG_PATH, encoding='utf-8'))
    except Exception:
        chosen_log_path = FALLBACK_LOG_PATH
        handlers.append(logging.FileHandler(FALLBACK_LOG_PATH, encoding='utf-8'))
    # Keep a secondary log in runtime dir when possible for troubleshooting.
    if chosen_log_path != FALLBACK_LOG_PATH:
        try:
            handlers.append(logging.FileHandler(FALLBACK_LOG_PATH, encoding='utf-8'))
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True,
    )
    return chosen_log_path


def encrypt_api_key(api_key: str) -> tuple[str, str]:
    """Encrypt an API key and return both the ciphertext and the key used.

    Parameters
    ----------
    api_key : str
        The plaintext API key.

    Returns
    -------
    tuple[str, str]
        A tuple of the encrypted key (base64 string) and the base64
        representation of the Fernet key used for encryption.
    """
    key = Fernet.generate_key()
    cipher_suite = Fernet(key)
    encrypted = cipher_suite.encrypt(api_key.encode('utf-8'))
    return encrypted.decode('utf-8'), key.decode('utf-8')


def decrypt_api_key(encrypted_key: str, fernet_key: str) -> str:
    """Decrypt an encrypted API key using the provided Fernet key.

    Parameters
    ----------
    encrypted_key : str
        The encrypted API key (base64 encoded string).
    fernet_key : str
        The base64 encoded key used for encryption.

    Returns
    -------
    str
        The decrypted plaintext API key.
    """
    cipher_suite = Fernet(fernet_key.encode('utf-8'))
    decrypted = cipher_suite.decrypt(encrypted_key.encode('utf-8'))
    return decrypted.decode('utf-8')


def get_api_key(conf: dict) -> str | None:
    """Retrieve and, if necessary, encrypt the API key stored in config.

    The function first attempts to decrypt the API key if both
    `encrypted_key` and `encryption_key` are present. If only the
    `api_key` field is populated, it will encrypt the key, save the
    encrypted form back to the config, and clear the plaintext key.

    Parameters
    ----------
    conf : dict
        The configuration dictionary.

    Returns
    -------
    str | None
        The decrypted API key if available, otherwise None.
    """
    encrypted = conf.get('encrypted_key')
    enc_key = conf.get('encryption_key')
    plain = conf.get('api_key')
    if encrypted and enc_key:
        try:
            return decrypt_api_key(encrypted, enc_key)
        except Exception as e:
            logging.error(f"Error decrypting API key: {e}")
            return None
    if plain:
        # Encrypt and persist
        encrypted_key, key = encrypt_api_key(plain)
        conf['encrypted_key'] = encrypted_key
        conf['encryption_key'] = key
        conf['api_key'] = ""
        save_config(conf)
        return decrypt_api_key(encrypted_key, key)
    return None


def set_api_key(conf: dict, api_key: str) -> str | None:
    """Encrypt and store an API key in config, then return plaintext key."""
    cleaned_key = api_key.strip()
    if not cleaned_key:
        return None
    try:
        encrypted_key, key = encrypt_api_key(cleaned_key)
        conf['api_key'] = ""
        conf['encrypted_key'] = encrypted_key
        conf['encryption_key'] = key
        save_config(conf)
        return cleaned_key
    except Exception as exc:
        logging.error(f"Failed to save API key: {exc}")
        return None


def prompt_for_api_key(config_path: Path) -> str | None:
    """Prompt user for Gemini API key via console or a simple GUI dialog."""
    message = (
        "Gemini API key is not configured.\n"
        f"Enter your key now. It will be encrypted in:\n{config_path}\n"
    )
    try:
        if sys.stdin and sys.stdin.isatty():
            print(message)
            try:
                key = getpass.getpass("Gemini API key (input hidden): ").strip()
            except Exception:
                key = input("Gemini API key: ").strip()
            return key or None
    except Exception as exc:
        logging.error(f"Console API prompt failed: {exc}")
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(
            "Vision Assistance App",
            "Gemini API key is not configured.\n"
            "Please enter it now. It will be encrypted and stored locally.",
            parent=root,
        )
        key = simpledialog.askstring(
            "Vision Assistance App",
            f"Enter Gemini API key.\nConfig file:\n{config_path}",
            show="*",
            parent=root,
        )
        root.destroy()
        if key:
            return key.strip() or None
    except Exception as exc:
        logging.error(f"GUI API prompt failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# Speech output

def init_speech_engine() -> pyttsx3.Engine:
    """Initialise the speech synthesis engine with sensible defaults."""
    engine = pyttsx3.init()
    # Optionally adjust voice properties here (rate, volume, voice)
    engine.setProperty('volume', 1.0)  # full volume
    engine.setProperty('rate', 165)    # clearer speaking speed
    return engine


def speak(
    engine: pyttsx3.Engine,
    text: str,
    interrupt: bool = False,
    repeat: int = 1,
) -> None:
    """Speak the given text asynchronously."""
    # Serialize all speech calls to avoid overlapping narration.
    if not hasattr(speak, "_lock"):
        speak._lock = threading.Lock()
    if not hasattr(speak, "_active_ps"):
        speak._active_ps = None
    if not hasattr(speak, "_active_proc"):
        speak._active_proc = None
    if not hasattr(speak, "_vbs_path"):
        speak._vbs_path = None
    if not hasattr(speak, "_stop_event"):
        speak._stop_event = threading.Event()

    def _speak_via_pyttsx3(utterance: str) -> None:
        if speak._stop_event.is_set():
            return
        # Keep a local fallback in case PowerShell speech fails.
        logging.info("Speech backend: pyttsx3")
        engine.say(utterance)
        engine.runAndWait()

    def _ensure_vbs_script() -> str:
        vbs_code = (
            'Set voice = CreateObject("SAPI.SpVoice")\n'
            'Set audio = CreateObject("SAPI.SpMMAudioOut")\n'
            "audio.DeviceId = 0\n"
            "audio.Volume = 100\n"
            "Set voice.AudioOutputStream = audio\n"
            "voice.Volume = 100\n"
            "voice.Rate = -1\n"
            "text = WScript.StdIn.ReadAll\n"
            "voice.Speak text\n"
        )
        if not speak._vbs_path:
            fd, script_path = tempfile.mkstemp(suffix=".vbs", prefix="vision_speech_")
            os.close(fd)
            speak._vbs_path = script_path
        Path(speak._vbs_path).write_text(vbs_code, encoding="utf-8")
        return speak._vbs_path

    def _speak_via_cscript(utterance: str) -> bool:
        if speak._stop_event.is_set():
            return True
        script_path = _ensure_vbs_script()
        proc = subprocess.Popen(
            ["cscript.exe", "//NoLogo", script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        speak._active_proc = proc
        _, stderr_text = proc.communicate(utterance)
        speak._active_proc = None
        if speak._stop_event.is_set():
            logging.info("Speech interrupted during cscript playback.")
            return True
        if proc.returncode != 0:
            logging.error(
                f"cscript speech failed (rc={proc.returncode}): {stderr_text.strip()}"
            )
            return False
        logging.info("Speech backend: cscript")
        return True

    def _speak_via_powershell(utterance: str) -> None:
        if speak._stop_event.is_set():
            return
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.SetOutputToDefaultAudioDevice(); "
            "$s.Volume = 100; "
            "$s.Rate = -1; "
            "$text = [Console]::In.ReadToEnd(); "
            "$s.Speak($text);"
        )
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        speak._active_ps = proc
        speak._active_proc = proc
        _, stderr_text = proc.communicate(utterance)
        speak._active_proc = None
        if speak._stop_event.is_set():
            logging.info("Speech interrupted during PowerShell playback.")
            speak._active_ps = None
            return
        if proc.returncode != 0:
            logging.error(
                f"PowerShell speech failed (rc={proc.returncode}): "
                f"{stderr_text.strip()}"
            )
            _speak_via_pyttsx3(utterance)
        else:
            logging.info("Speech backend: powershell")
        speak._active_ps = None

    def _speak_via_wave_file(utterance: str) -> bool:
        if speak._stop_event.is_set():
            return True
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="vision_tts_")
        os.close(fd)
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Volume = 100; "
            "$s.Rate = -1; "
            "$text = [Console]::In.ReadToEnd(); "
            "$outPath = $env:VISION_TTS_WAV_PATH; "
            "$s.SetOutputToWaveFile($outPath); "
            "$s.Speak($text); "
            "$s.Dispose();"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                input=utterance,
                text=True,
                capture_output=True,
                env={**os.environ, "VISION_TTS_WAV_PATH": wav_path},
            )
            if proc.returncode != 0:
                logging.error(
                    f"Wave synthesis failed (rc={proc.returncode}): "
                    f"{proc.stderr.strip()}"
                )
                return False
            if speak._stop_event.is_set():
                return True
            try:
                with wave.open(wav_path, "rb") as wav_file:
                    frame_count = wav_file.getnframes()
                    frame_rate = wav_file.getframerate()
                    duration_seconds = (
                        frame_count / float(frame_rate) if frame_rate else 0.0
                    )
            except Exception:
                duration_seconds = 8.0
            winsound.PlaySound(
                wav_path,
                winsound.SND_FILENAME | winsound.SND_ASYNC,
            )
            deadline = time.time() + duration_seconds + 0.15
            while time.time() < deadline:
                if speak._stop_event.is_set():
                    winsound.PlaySound(None, winsound.SND_PURGE)
                    logging.info("Speech interrupted during wave playback.")
                    return True
                time.sleep(0.05)
            logging.info("Speech backend: wave-file")
            return True
        except Exception as exc:
            logging.error(f"Wave playback failed: {exc}")
            return False
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass

    if speak._stop_event.is_set():
        logging.info("Speech suppressed due to active user stop request.")
        return
    if interrupt and speak._active_proc is not None:
        try:
            speak._active_proc.terminate()
        except Exception:
            pass
    with speak._lock:
        for _ in range(max(1, repeat)):
            if speak._stop_event.is_set():
                break
            if _speak_via_wave_file(text):
                continue
            if speak._stop_event.is_set():
                break
            if _speak_via_cscript(text):
                continue
            if speak._stop_event.is_set():
                break
            _speak_via_powershell(text)


def clear_speech_stop_request() -> None:
    """Allow future speech output after a user-triggered stop."""
    if not hasattr(speak, "_stop_event"):
        speak._stop_event = threading.Event()
    speak._stop_event.clear()


def stop_current_speech(engine: pyttsx3.Engine | None = None) -> None:
    """Immediately interrupt active speech and suppress pending narration."""
    if not hasattr(speak, "_stop_event"):
        speak._stop_event = threading.Event()
    if not hasattr(speak, "_active_proc"):
        speak._active_proc = None
    speak._stop_event.set()
    active_proc = speak._active_proc
    if active_proc is not None:
        try:
            active_proc.terminate()
        except Exception:
            pass
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
    if engine is not None:
        try:
            engine.stop()
        except Exception:
            pass


def safe_beep(frequency: int = 1000, duration_ms: int = 80) -> None:
    """Play a short beep without raising exceptions to callers."""
    try:
        winsound.Beep(frequency, duration_ms)
    except Exception:
        try:
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass


def play_beep_pattern(pattern: list[tuple[int, int]], async_mode: bool = True) -> None:
    """Play a sequence of (frequency, duration_ms) beeps."""
    def _run() -> None:
        for freq, duration in pattern:
            safe_beep(freq, duration)
            time.sleep(0.04)
    if async_mode:
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()


def play_audio_cue(sound_alias: str, fallback_pattern: list[tuple[int, int]]) -> None:
    """Play a clearly audible cue sound, falling back to tone beeps."""
    try:
        winsound.PlaySound(sound_alias, winsound.SND_ALIAS | winsound.SND_SYNC)
    except Exception:
        play_beep_pattern(fallback_pattern, async_mode=False)


def play_working_tick() -> None:
    """Play a short periodic tick while AI processing is active."""
    try:
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_SYNC)
    except Exception:
        safe_beep(980, 70)


def start_progress_beep_loop(stop_event: threading.Event) -> threading.Thread:
    """Start periodic audible ticks to indicate active AI processing."""
    def _run() -> None:
        while not stop_event.is_set():
            play_working_tick()
            stop_event.wait(1.2)
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def transcribe_from_microphone(
    timeout_seconds: int = 8,
    cancel_event: threading.Event | None = None,
    stop_event: threading.Event | None = None,
) -> str | None:
    """Capture short dictation from default microphone via Windows speech API."""
    if not hasattr(transcribe_from_microphone, "_active_proc_lock"):
        transcribe_from_microphone._active_proc_lock = threading.Lock()
    if not hasattr(transcribe_from_microphone, "_active_proc"):
        transcribe_from_microphone._active_proc = None

    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
        "$recognizer.SetInputToDefaultAudioDevice(); "
        "$grammar = New-Object System.Speech.Recognition.DictationGrammar; "
        "$recognizer.LoadGrammar($grammar); "
        f"$result = $recognizer.Recognize([TimeSpan]::FromSeconds({timeout_seconds})); "
        "if ($result -ne $null) { "
        "  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "  Write-Output $result.Text "
        "}"
    )
    try:
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with transcribe_from_microphone._active_proc_lock:
            transcribe_from_microphone._active_proc = proc
        deadline = time.time() + max(timeout_seconds + 5, 12)
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
                logging.info("Microphone transcription canceled by user.")
                return None
            if stop_event is not None and stop_event.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
                logging.info("Microphone transcription stopped by user submit.")
                return None
            if time.time() > deadline:
                try:
                    proc.terminate()
                except Exception:
                    pass
                logging.error("Microphone transcription timed out.")
                return None
            time.sleep(0.05)
        stdout_text, stderr_text = proc.communicate()
        if stop_event is not None and stop_event.is_set():
            return None
        if proc.returncode != 0:
            logging.error(
                f"Microphone transcription failed (rc={proc.returncode}): "
                f"{(stderr_text or '').strip()}"
            )
            return None
        transcript = (stdout_text or "").strip()
        return transcript or None
    except Exception as exc:
        logging.error(f"Microphone transcription error: {exc}")
        return None
    finally:
        with transcribe_from_microphone._active_proc_lock:
            transcribe_from_microphone._active_proc = None


def cancel_active_transcription() -> None:
    """Cancel active microphone transcription process if running."""
    if not hasattr(transcribe_from_microphone, "_active_proc_lock"):
        return
    with transcribe_from_microphone._active_proc_lock:
        active_proc = transcribe_from_microphone._active_proc
    if active_proc is None:
        return
    try:
        if active_proc.poll() is None:
            active_proc.terminate()
            logging.info("Canceled active microphone transcription process.")
    except Exception as exc:
        logging.error(f"Failed to cancel microphone transcription: {exc}")


# ---------------------------------------------------------------------------
# Gemini interaction

def query_screenshot(
    api_key: str,
    image_bytes: bytes,
    prompt: str,
    cancel_event: threading.Event | None = None,
) -> str:
    """Send screenshot and prompt to Gemini and return text response.

    Parameters
    ----------
    api_key : str
        The user's Gemini API key.
    image_bytes : bytes
        The raw bytes of the PNG image.
    prompt : str
        Instruction or question to answer about the screenshot.

    Returns
    -------
    str
        The model's textual response. If an error
        occurs, an appropriate message is returned instead.
    """
    if not hasattr(query_screenshot, "_active_client_lock"):
        query_screenshot._active_client_lock = threading.Lock()
    if not hasattr(query_screenshot, "_active_client"):
        query_screenshot._active_client = None
    if cancel_event is not None and cancel_event.is_set():
        return "Request canceled."
    # We create a client per request to ensure resources are freed.
    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        logging.error(f"Failed to instantiate Gemini client: {exc}")
        return "Failed to initialise the Gemini client."
    try:
        with query_screenshot._active_client_lock:
            query_screenshot._active_client = client
        contents = [
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
        ]
        response_text = ""
        for chunk in client.models.generate_content_stream(
            model='gemini-2.5-flash', contents=contents
        ):
            if cancel_event is not None and cancel_event.is_set():
                logging.info("Gemini request canceled by user.")
                return "Request canceled."
            response_text += chunk.text or ""
        if cancel_event is not None and cancel_event.is_set():
            logging.info("Gemini request canceled after stream.")
            return "Request canceled."
        return response_text.strip() or "No description returned."
    except Exception as exc:
        if cancel_event is not None and cancel_event.is_set():
            logging.info("Gemini request aborted after user cancel.")
            return "Request canceled."
        logging.error(f"Error during Gemini API call: {exc}")
        return f"Error describing image: {exc}"
    finally:
        with query_screenshot._active_client_lock:
            if query_screenshot._active_client is client:
                query_screenshot._active_client = None
        # Ensure the underlying HTTP connections are closed.
        try:
            client.close()
        except Exception:
            pass


def cancel_active_query() -> None:
    """Cancel active Gemini request if one is currently running."""
    if not hasattr(query_screenshot, "_active_client_lock"):
        return
    with query_screenshot._active_client_lock:
        active_client = query_screenshot._active_client
    if active_client is None:
        return
    try:
        active_client.close()
        logging.info("Canceled active Gemini request.")
    except Exception as exc:
        logging.error(f"Failed to cancel active Gemini request: {exc}")


def describe_screenshot(
    api_key: str,
    image_bytes: bytes,
    cancel_event: threading.Event | None = None,
) -> str:
    """Describe screenshot content for a visually impaired user."""
    return query_screenshot(
        api_key,
        image_bytes,
        "Describe this screenshot for a blind user.",
        cancel_event=cancel_event,
    )


# ---------------------------------------------------------------------------
# Hot‑key functionality

class VisionAssistant:
    """Main application class that orchestrates hot‑key handling and
    interactions with the Gemini API."""

    def __init__(self) -> None:
        self.active_log_path = configure_logging()
        self.conf = load_config()
        self.api_key: str | None = get_api_key(self.conf)
        self.engine = init_speech_engine()
        self.running = True
        self._capture_lock = threading.Lock()
        self._task_cancel_event = threading.Event()
        self._task_state_lock = threading.Lock()
        self._active_task_name: str | None = None
        self._follow_up_listening_event = threading.Event()
        self._follow_up_submit_event = threading.Event()
        self._description_sections: list[str] = []
        self._current_detail_index: int = -1
        self._state_lock = threading.Lock()
        logging.info(f"Application started. Primary log: {self.active_log_path}")
        self.show_instructions()
        # Register hot-keys
        keyboard.add_hotkey('ctrl+m', self._on_capture_hotkey)
        keyboard.add_hotkey('ctrl+n', self._on_follow_up_hotkey)
        keyboard.add_hotkey('ctrl+shift+s', self._on_stop_speaking_hotkey)
        keyboard.add_hotkey('ctrl+shift+x', self._on_cancel_task_hotkey)
        keyboard.add_hotkey('ctrl+alt+k', self._on_set_api_key_hotkey)
        keyboard.add_hotkey('ctrl+right', self._on_next_detail_hotkey)
        keyboard.add_hotkey('ctrl+down', self._on_next_detail_hotkey)
        keyboard.add_hotkey('ctrl+left', self._on_previous_detail_hotkey)
        keyboard.add_hotkey('ctrl+up', self._on_previous_detail_hotkey)
        keyboard.add_hotkey('ctrl+shift+q', self.stop)
        self._ensure_api_key_configured()

    def show_instructions(self) -> None:
        """Display and speak usage instructions."""
        instructions = (
            "Welcome to the Vision Assistance App.\n"
            "\n"
            "Instructions:\n"
            "  - Press CTRL+M at any time to capture the screen and hear a summary.\n"
            "  - Press CTRL+N to start a voice follow-up question.\n"
            "  - Press CTRL+N again to stop recording and send it immediately.\n"
            "  - Press CTRL+SHIFT+S anytime to stop current speech immediately.\n"
            "  - Press CTRL+SHIFT+X to cancel the current capture or follow-up task.\n"
            "  - You will hear periodic ticks while AI analysis is in progress.\n"
            "  - Press CTRL+ALT+K to set or update Gemini API key.\n"
            "  - Press CTRL+RIGHT or CTRL+DOWN for the next detail.\n"
            "  - Press CTRL+LEFT or CTRL+UP for the previous detail.\n"
            "  - Press CTRL+SHIFT+Q to exit the application.\n"
            "  - If API key is missing, the app will prompt you and encrypt it automatically.\n"
            f"  - Config file is auto-created at '{CONFIG_PATH}'.\n"
            f"  - Logs are stored in '{self.active_log_path}'.\n"
        )
        print(instructions)
        # Speak asynchronously in another thread to avoid blocking
        threading.Thread(target=speak, args=(self.engine, instructions), daemon=True).start()

    def _on_capture_hotkey(self) -> None:
        """Callback executed when the capture hot?key is pressed."""
        stop_current_speech(self.engine)
        if not self._capture_lock.acquire(timeout=0.8):
            print("Capture already in progress. Press Ctrl+Shift+X to cancel it.")
            play_beep_pattern([(420, 90), (380, 90)])
            return
        clear_speech_stop_request()
        self._task_cancel_event.clear()
        self._set_active_task("capture")
        play_beep_pattern([(740, 60), (900, 70)])
        print("Hotkey detected: capturing screen...")
        threading.Thread(target=self._capture_and_describe, daemon=True).start()

    def _on_follow_up_hotkey(self) -> None:
        """Capture voice follow-up question and answer based on current screen."""
        if self._follow_up_listening_event.is_set():
            self._follow_up_submit_event.set()
            cancel_active_transcription()
            print("Stopping recording and sending your follow-up question...")
            play_audio_cue("SystemAsterisk", [(980, 90), (1180, 110)])
            return
        stop_current_speech(self.engine)
        if not self._capture_lock.acquire(timeout=0.8):
            print("Capture already in progress. Press Ctrl+Shift+X to cancel it.")
            play_beep_pattern([(420, 90), (380, 90)])
            return
        clear_speech_stop_request()
        self._task_cancel_event.clear()
        self._set_active_task("follow-up")
        self._follow_up_submit_event.clear()
        play_beep_pattern([(760, 60), (1040, 80)])
        print("Follow-up hotkey detected: preparing voice recording...")
        threading.Thread(target=self._handle_follow_up_query, daemon=True).start()

    def _on_stop_speaking_hotkey(self) -> None:
        """Interrupt the current narration immediately."""
        logging.info("Speech stop hot-key pressed")
        stop_current_speech(self.engine)
        print("Speech stopped. You can trigger the next action now.")
        play_beep_pattern([(500, 70), (420, 90)])

    def _set_active_task(self, task_name: str | None) -> None:
        """Track the currently running long task for cancellation feedback."""
        with self._task_state_lock:
            self._active_task_name = task_name

    def _get_active_task(self) -> str | None:
        """Return the name of the currently running long task, if any."""
        with self._task_state_lock:
            return self._active_task_name

    def _on_cancel_task_hotkey(self) -> None:
        """Cancel in-progress capture/follow-up processing immediately."""
        active_task = self._get_active_task()
        self._task_cancel_event.set()
        self._follow_up_submit_event.set()
        self._follow_up_listening_event.clear()
        cancel_active_transcription()
        cancel_active_query()
        stop_current_speech(self.engine)
        if active_task:
            logging.info(f"Task cancel hot-key pressed. Active task: {active_task}")
            print(f"{active_task.capitalize()} task canceled. Ready for next command.")
        else:
            logging.info("Task cancel hot-key pressed with no active long task.")
            print("No capture task was running. Speech was stopped.")
        play_beep_pattern([(460, 70), (390, 90), (320, 110)])

    def _record_follow_up_question(
        self,
        max_record_seconds: int = 30,
        chunk_seconds: int = 3,
    ) -> str | None:
        """Record follow-up dictation in chunks so users can submit early."""
        chunks: list[str] = []
        started_at = time.time()
        while (time.time() - started_at) < max_record_seconds:
            if self._task_cancel_event.is_set():
                return None
            if self._follow_up_submit_event.is_set():
                break
            remaining = max_record_seconds - int(time.time() - started_at)
            timeout = max(1, min(chunk_seconds, remaining))
            chunk = transcribe_from_microphone(
                timeout_seconds=timeout,
                cancel_event=self._task_cancel_event,
                stop_event=self._follow_up_submit_event,
            )
            if self._task_cancel_event.is_set():
                return None
            if chunk:
                text = chunk.strip()
                if text:
                    chunks.append(text)
                    print(f"Heard: {text}")
            if self._follow_up_submit_event.is_set():
                break
        if not chunks:
            return None
        return " ".join(chunks)

    def _capture_screenshot_bytes(self) -> bytes | None:
        """Capture current screen and return image bytes."""
        try:
            screenshot = pyautogui.screenshot()
            buf = io.BytesIO()
            screenshot.save(buf, format='PNG')
            return buf.getvalue()
        except Exception as exc:
            logging.error(f"Failed to take screenshot: {exc}")
            speak(self.engine, f"Failed to take screenshot: {exc}")
            print(f"Failed to take screenshot: {exc}")
            play_beep_pattern([(420, 90), (380, 90), (340, 90)])
            return None

    def _capture_and_describe(self) -> None:
        """Capture the current screen and announce a description."""
        progress_stop_event: threading.Event | None = None
        progress_thread: threading.Thread | None = None
        try:
            logging.info("Capture hot?key pressed")
            if self._task_cancel_event.is_set():
                logging.info("Capture task canceled before execution.")
                return
            if not self.api_key:
                self._ensure_api_key_configured()
                if not self.api_key:
                    message = (
                        "API key is still missing. Please provide it when prompted, "
                        "or update config.json and try again."
                    )
                    speak(self.engine, message)
                    print(message)
                    play_beep_pattern([(420, 90), (380, 90), (340, 90)])
                    return
            if self._task_cancel_event.is_set():
                print("Capture canceled.")
                return
            img_bytes = self._capture_screenshot_bytes()
            if not img_bytes:
                return
            if self._task_cancel_event.is_set():
                print("Capture canceled.")
                return
            play_beep_pattern([(1100, 70)])
            # Send to Gemini and speak the description
            print("Analyzing screenshot. Please wait...")
            progress_stop_event = threading.Event()
            progress_thread = start_progress_beep_loop(progress_stop_event)
            description = describe_screenshot(
                self.api_key,
                img_bytes,
                cancel_event=self._task_cancel_event,
            )
            progress_stop_event.set()
            if progress_thread.is_alive():
                progress_thread.join(timeout=0.2)
            if self._task_cancel_event.is_set():
                logging.info("Capture task canceled while waiting for model response.")
                print("Capture canceled.")
                return
            logging.info(f"Gemini description: {description}")
            print(f"Gemini description: {description}")
            self._store_description_details(description)
            summary = self._build_summary(description)
            print("Speaking summary now...")
            play_beep_pattern([(1250, 90), (1500, 120)])
            speak(self.engine, "Summary is ready.", interrupt=True)
            speak(self.engine, f"Summary. {summary}")
            speak(
                self.engine,
                "Press control plus right arrow for next detail. "
                "Press control plus left arrow for previous detail.",
            )
        finally:
            if progress_stop_event is not None:
                progress_stop_event.set()
            if progress_thread is not None and progress_thread.is_alive():
                progress_thread.join(timeout=0.2)
            self._set_active_task(None)
            self._capture_lock.release()

    def _handle_follow_up_query(self) -> None:
        """Handle follow-up voice question for current screen."""
        progress_stop_event: threading.Event | None = None
        progress_thread: threading.Thread | None = None
        try:
            logging.info("Follow-up hotkey pressed")
            if self._task_cancel_event.is_set():
                logging.info("Follow-up task canceled before execution.")
                return
            if not self.api_key:
                self._ensure_api_key_configured()
                if not self.api_key:
                    message = (
                        "API key is still missing. Please provide it when prompted, "
                        "or update config.json and try again."
                    )
                    speak(self.engine, message)
                    print(message)
                    play_beep_pattern([(420, 90), (380, 90), (340, 90)])
                    return
            speak(
                self.engine,
                "Recording mode. Ask your follow-up question after the beep. "
                "Press control plus N again to send immediately.",
            )
            if self._task_cancel_event.is_set():
                print("Follow-up canceled.")
                return
            print("Follow-up recording started. Speak now, then press Ctrl+N to send.")
            self._follow_up_submit_event.clear()
            self._follow_up_listening_event.set()
            play_audio_cue("SystemExclamation", [(1320, 140), (1560, 170)])
            transcript = self._record_follow_up_question(
                max_record_seconds=30,
                chunk_seconds=3,
            )
            self._follow_up_listening_event.clear()
            play_audio_cue("SystemAsterisk", [(900, 80), (1060, 100)])
            if self._task_cancel_event.is_set():
                logging.info("Follow-up canceled during question recording.")
                print("Follow-up canceled.")
                return
            if not transcript:
                message = (
                    "I could not understand the question. "
                    "Please press control plus N and try again."
                )
                print(message)
                speak(self.engine, message)
                play_beep_pattern([(420, 90), (380, 90)])
                return
            logging.info(f"Follow-up transcript: {transcript}")
            print(f"Follow-up question: {transcript}")
            if self._task_cancel_event.is_set():
                print("Follow-up canceled.")
                return
            img_bytes = self._capture_screenshot_bytes()
            if not img_bytes:
                return
            if self._task_cancel_event.is_set():
                print("Follow-up canceled.")
                return
            play_beep_pattern([(1100, 70)])
            print("Analyzing follow-up question. Please wait...")
            progress_stop_event = threading.Event()
            progress_thread = start_progress_beep_loop(progress_stop_event)
            prompt = (
                "You are assisting a blind user. "
                "Answer the user's question using only this screenshot. "
                "Be clear, concise, and practical. "
                f"User question: {transcript}"
            )
            answer = query_screenshot(
                self.api_key,
                img_bytes,
                prompt,
                cancel_event=self._task_cancel_event,
            )
            progress_stop_event.set()
            if progress_thread.is_alive():
                progress_thread.join(timeout=0.2)
            if self._task_cancel_event.is_set():
                logging.info("Follow-up canceled while waiting for model response.")
                print("Follow-up canceled.")
                return
            logging.info(f"Follow-up answer: {answer}")
            print(f"Follow-up answer: {answer}")
            play_beep_pattern([(1250, 90), (1500, 120)])
            speak(self.engine, answer, interrupt=True)
        finally:
            self._follow_up_listening_event.clear()
            self._follow_up_submit_event.clear()
            if progress_stop_event is not None:
                progress_stop_event.set()
            if progress_thread is not None and progress_thread.is_alive():
                progress_thread.join(timeout=0.2)
            self._set_active_task(None)
            self._capture_lock.release()

    def _on_set_api_key_hotkey(self) -> None:
        """Prompt user to set or update API key."""
        stop_current_speech(self.engine)
        clear_speech_stop_request()
        threading.Thread(target=self._set_api_key_from_hotkey, daemon=True).start()

    def _set_api_key_from_hotkey(self) -> None:
        """Handle API key update triggered by hot-key."""
        logging.info("API key update hot-key pressed")
        play_beep_pattern([(950, 70), (1200, 90)])
        self._ensure_api_key_configured(force_prompt=True)

    def _ensure_api_key_configured(self, force_prompt: bool = False) -> None:
        """Ensure API key exists; if missing, prompt user and save encrypted."""
        if self.api_key and not force_prompt:
            return
        if force_prompt:
            speak(
                self.engine,
                "API key update requested. Please enter your Gemini API key now.",
            )
        else:
            speak(
                self.engine,
                "Gemini API key is not configured. Please enter it now.",
            )
        entered_key = prompt_for_api_key(CONFIG_PATH)
        if not entered_key:
            if force_prompt:
                print("API key update canceled. Existing value unchanged.")
                speak(self.engine, "API key update canceled.")
                play_beep_pattern([(420, 90), (380, 90)])
            else:
                print(
                    f"No API key provided. You can set it later in '{CONFIG_PATH}'."
                )
            return
        saved_key = set_api_key(self.conf, entered_key)
        if not saved_key:
            speak(
                self.engine,
                "Failed to save API key. Please update config.json manually.",
            )
            print(f"Failed to save API key in '{CONFIG_PATH}'.")
            play_beep_pattern([(420, 90), (380, 90), (340, 90)])
            return
        self.api_key = saved_key
        success_message = (
            f"API key saved and encrypted in '{CONFIG_PATH}'."
        )
        print(success_message)
        if force_prompt:
            speak(self.engine, "API key updated successfully.")
        else:
            speak(self.engine, "API key saved successfully.")
        play_beep_pattern([(1200, 90), (1450, 120)])

    def _normalize_for_speech(self, text: str) -> str:
        """Normalize model output so TTS reads it clearly."""
        cleaned = text.replace("\n", " ")
        cleaned = re.sub(r"[*_`#]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _store_description_details(self, description: str) -> None:
        """Split Gemini output into detail chunks for keyboard navigation."""
        normalized = self._normalize_for_speech(description)
        parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', normalized) if p.strip()]
        if not parts:
            parts = [normalized or "No details available."]
        with self._state_lock:
            self._description_sections = parts
            self._current_detail_index = -1

    def _build_summary(self, description: str) -> str:
        """Build a short summary from the first one or two sentences."""
        normalized = self._normalize_for_speech(description)
        parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', normalized) if p.strip()]
        if not parts:
            return normalized or "No description returned."
        return " ".join(parts[:2])

    def _on_next_detail_hotkey(self) -> None:
        """Read the next detail chunk."""
        stop_current_speech(self.engine)
        if not self._capture_lock.acquire(timeout=0.8):
            print("Action still in progress. Please try again.")
            play_beep_pattern([(420, 90), (380, 90)])
            return
        clear_speech_stop_request()
        threading.Thread(target=self._navigate_detail, args=(1,), daemon=True).start()

    def _on_previous_detail_hotkey(self) -> None:
        """Read the previous detail chunk."""
        stop_current_speech(self.engine)
        if not self._capture_lock.acquire(timeout=0.8):
            print("Action still in progress. Please try again.")
            play_beep_pattern([(420, 90), (380, 90)])
            return
        clear_speech_stop_request()
        threading.Thread(target=self._navigate_detail, args=(-1,), daemon=True).start()

    def _navigate_detail(self, step: int) -> None:
        """Move through indexed detail chunks and read the selected one aloud."""
        try:
            with self._state_lock:
                details = self._description_sections
                index = self._current_detail_index
                if not details:
                    message = "No details available yet. Press control plus M first."
                else:
                    if index == -1:
                        index = 0 if step > 0 else len(details) - 1
                    elif step > 0 and index < len(details) - 1:
                        index += 1
                    elif step < 0 and index > 0:
                        index -= 1
                    self._current_detail_index = index
                    message = f"Detail {index + 1} of {len(details)}. {details[index]}"
            print(message)
            speak(self.engine, message)
        finally:
            self._capture_lock.release()

    def stop(self, speak_farewell: bool = True, force_exit: bool = True) -> None:
        """Stop the application and clean up resources."""
        if not self.running:
            return
        logging.info("Shutdown requested. Exiting application.")
        self.running = False
        self._task_cancel_event.set()
        self._follow_up_submit_event.set()
        self._follow_up_listening_event.clear()
        cancel_active_transcription()
        cancel_active_query()
        self._set_active_task(None)
        # Unregister hot-keys first so no more callbacks are queued.
        keyboard.unhook_all_hotkeys()
        if speak_farewell:
            stop_current_speech(self.engine)
            clear_speech_stop_request()
            speak(self.engine, "Exiting Vision Assistance App. Goodbye.")
        if force_exit:
            # Keep force-exit only for hot-key shutdown behavior.
            time.sleep(0.2)
            os._exit(0)


def main() -> None:
    """Entry point for the application."""
    instance_lock = SingleInstanceLock(LOCK_PATH)
    if not instance_lock.acquire():
        print("Vision Assistance App is already running. Close the other instance first.")
        return
    assistant = VisionAssistant()
    # Keep the main thread alive while the hot-key listener is running
    try:
        while assistant.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Stopping...")
        assistant.stop(speak_farewell=False, force_exit=False)
    finally:
        instance_lock.release()


if __name__ == '__main__':
    main()
