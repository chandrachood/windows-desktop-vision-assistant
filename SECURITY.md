# Security Policy

## Supported Versions

This project currently supports the latest version on the default branch.

## Reporting a Vulnerability

If you discover a security issue, do not open a public issue.

Use GitHub private reporting:

- `https://github.com/<owner>/<repo>/security/advisories/new`

Include:
- clear description of the vulnerability,
- steps to reproduce,
- potential impact,
- suggested remediation (if available).

If private reporting is unavailable, open a public issue with minimal detail and ask maintainers to move the report to a private channel.

## Response Targets

- Initial maintainer response: within 72 hours
- Triage decision: within 7 days
- Fix timeline: depends on severity and complexity, communicated after triage

## Disclosure

- Please allow maintainers reasonable time to investigate and release a fix before public disclosure.
- Credit reporters in release notes unless anonymity is requested.

## Security Notes for This Project

- Never commit `config.json` with real credentials.
- Never commit `app.log` if it contains user screen descriptions.
- Rotate Gemini API keys immediately if exposed.
- Validate dependency updates before release.
