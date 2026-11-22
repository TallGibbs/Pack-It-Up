# Hackathon Export (Skills, Preferences & Learnings)

Exported from the temporary hackathon Antigravity/Gemini account on Nov 21, 2026 before account deletion. Contains **no API keys, credentials, or personal account tokens**.

## Contents

- [`LEARNINGS.md`](LEARNINGS.md) — Curated technical and workflow learnings from building **Pack It Up** at Gemini 4 NYC.
- `preferences/` — Global user rules and formatting preferences:
  - `GEMINI.md` (from `~/.gemini/GEMINI.md`)
  - `preferences.md` (from `~/.gemini/config/rules/preferences.md`)
- `skills/` — Installed plugin skills (excluding any auth/account state):
  - `skills/gemini-api/` (`gemini-api-dev`, `gemini-api-cli`, `gemini-live-api-dev`, `gemini-omni-flash-api`)
  - `skills/gdrive/` (`gdrive`)
- Note: The repo's own Gemini output workflow skill is already tracked at [`../.claude/skills/gemini-outputs/`](../.claude/skills/gemini-outputs/).

## How to restore on a new account

1. **Preferences / Rules:**
   ```sh
   mkdir -p ~/.gemini/config/rules
   cp hackathon-export/preferences/GEMINI.md ~/.gemini/GEMINI.md
   cp hackathon-export/preferences/preferences.md ~/.gemini/config/rules/preferences.md
   ```
2. **Skills:**
   Copy any skill folder from `hackathon-export/skills/` into `~/.gemini/config/skills/` (or install the `gemini-api` / `gdrive` plugins via the Antigravity Plugins Manager).
