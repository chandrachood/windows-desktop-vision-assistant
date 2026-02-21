# Contributing

Thanks for contributing to Vision Assistance App.

## Development Setup

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Copy the config template:

```bash
copy config.example.json config.json
```

5. Add your Gemini API key in `config.json` (`api_key` field).

## Coding Guidelines

- Keep accessibility first in all UX decisions.
- Prefer clear, defensive error handling.
- Avoid introducing platform assumptions without documenting them.
- Keep user-facing language concise and screen-reader friendly.

## Local Validation

Before opening a pull request:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pip check
python -m py_compile main.py
```

Then run the app manually and validate:
- `Ctrl+M` capture and summary narration
- detail navigation with `Ctrl+Arrow`
- graceful shutdown (`Ctrl+Shift+Q` and `Ctrl+C`)

## Pull Request Process

1. Create a feature branch.
2. Keep PR scope focused.
3. Add or update documentation when behavior changes.
4. Include reproduction and test notes in the PR description.
5. Ensure no secrets or local logs are included.
6. Wait for CI checks (Python 3.10-3.12 compile matrix) to pass before requesting merge.

## Branch and Commit Guidance

- Suggested branch names:
  - `feat/<short-name>`
  - `fix/<short-name>`
  - `docs/<short-name>`
- Suggested commit prefix:
  - `feat:`
  - `fix:`
  - `docs:`
  - `chore:`

## Commit Hygiene

Do not commit:
- `config.json`
- `app.log`
- `venv/`
- `.vision_assistant.lock`

Use `config.example.json` for configuration examples.
