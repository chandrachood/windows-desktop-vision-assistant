# GitHub Setup Checklist

Use this checklist to publish and maintain the repository as a strong open-source project.

## 1. Pre-publish Local Cleanup

1. Ensure these files do not contain real secrets:
   - `config.json`
   - `app.log`
2. Confirm ignored local/runtime files are not staged:
   - `venv/`
   - `.vision_assistant.lock`
   - `*.wav`
3. Run local validation:

```bash
python -m py_compile main.py
```

## 2. Initialize Git (if this folder is not yet a repository)

Run from project root:

```bash
git init
git branch -M main
git add .
git commit -m "chore: initial open-source release"
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

## 3. Create Repository Metadata

In GitHub repository settings:

1. Description:
   - `Windows accessibility assistant that describes the current screen and supports voice follow-up.`
2. Topics:
   - `accessibility`
   - `screen-reader`
   - `visual-impairment`
   - `assistive-technology`
   - `python`
   - `windows`
   - `gemini`
3. Enable:
   - Issues
   - Discussions (recommended)
   - Wiki or Projects (optional)

## 4. Security & Dependency Settings

In `Settings -> Security`:

1. Enable private vulnerability reporting.
2. Enable Dependabot alerts.
3. Enable Dependabot security updates.
4. Confirm `.github/dependabot.yml` is active.

## 5. Required Community Files

Verify these are in `main`:

1. `README.md`
2. `LICENSE`
3. `CODE_OF_CONDUCT.md`
4. `CONTRIBUTING.md`
5. `SECURITY.md`
6. `SUPPORT.md`
7. `CHANGELOG.md`
8. `.github/CODEOWNERS`
9. `.github/workflows/ci.yml`
10. `.github/workflows/release-exe.yml`
11. `.github/ISSUE_TEMPLATE/*`
12. `.github/pull_request_template.md`

## 6. Update Placeholder URLs

After creating the GitHub repository, replace placeholder links:

1. `.github/ISSUE_TEMPLATE/config.yml`
2. `SECURITY.md` (if you add direct contact links there)

Replace `<owner>/<repo>` with your actual repository path.

## 7. Branch Protection (Main)

Create a branch protection rule or ruleset for `main`:

1. Require pull request before merging.
2. Require at least 1 approving review.
3. Require status checks to pass:
   - `Compile check (Python 3.10)`
   - `Compile check (Python 3.11)`
   - `Compile check (Python 3.12)`
4. Block force pushes.
5. Block branch deletion.
6. Require linear history (recommended).

## 8. Release Workflow

`.github/workflows/release-exe.yml` supports:

1. Manual trigger (`workflow_dispatch`)
2. Automatic EXE build when a release is published

Release assets expected:

1. `VisionAssistanceApp.exe`
2. `VisionAssistanceApp-windows.zip`
3. `config.example.json`

Suggested release flow:

1. Update `CHANGELOG.md`.
2. Create and push a tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

3. Create a GitHub release from the tag.
4. Confirm workflow completed and assets are attached.

## 9. Maintainer Hygiene

Before each release:

1. Verify no credentials leaked in current branch.
2. Rotate API keys immediately if leaked.
3. Run smoke test on Windows:
   - `Ctrl+M` capture and summary
   - detail navigation (`Ctrl+Arrow`)
   - cancel/stop controls (`Ctrl+Shift+S`, `Ctrl+Shift+X`)
   - graceful exit (`Ctrl+Shift+Q`)
4. Ensure docs reflect current behavior.
