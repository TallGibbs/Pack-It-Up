# Team memory

Shared memory for everyone working on Pack It Up: Chris, George, and any agent session (Claude Code, Antigravity, others). Agents start every session with no knowledge of earlier sessions or of sessions running in parallel. These files are how they find out.

This folder lives in the public build repo, [TallGibbs/Pack-It-Up](https://github.com/TallGibbs/Pack-It-Up). It moved here from the private planning repo on Nov 21 (see the decision log), so everything in it is public: write nothing you wouldn't publish. Build rules are in [AGENTS.md](../AGENTS.md).

## Files

| File | What goes in it | How to edit |
|---|---|---|
| [decisions.md](decisions.md) | Every decision the team made, newest at the bottom, with why and who decided | Append only. To change a decision, add a new entry that says which one it replaces |
| [sessions.md](sessions.md) | Who or what is working right now, in which repo and branch, on which files | Add your row when you start, update its status when you stop |
| [open-questions.md](open-questions.md) | Questions waiting on a person or the organizers, and ideas not yet decided | Move an item to `decisions.md` once it is decided |

Plans and specs stay in [`plan/`](../plan/). Memory records what was decided and who is doing what; it links to plans rather than repeating them.

## How to use it

**At the start of a session**
1. `git pull --rebase`.
2. Read [decisions.md](decisions.md) from the bottom up until you have the context you need, then [sessions.md](sessions.md) and [open-questions.md](open-questions.md).
3. Add your row to `sessions.md`: start time, session name, tool, repo and branch, the files or folders you will change, status `active`.
4. If another active session already claims files you need, don't edit them. Ask Chris or message that session.

**While working**
- When the user makes or confirms a decision, append it to `decisions.md` right away. Only things a person decided or agreed; never record your own guess as a decision.
- When you hit a question only a person or the organizers can answer, add it to `open-questions.md`.
- Commit memory edits on their own, in small commits (`memory: ...`), and push soon. Run `git pull --rebase` first. Because every file is append-only or one row per session, conflicts are rare and easy to resolve by keeping both sides.

**At the end of a session**
- Set your row in `sessions.md` to `done` or `paused`, with one line on what is left and where (branch, PR, unpushed commits).

## Rules

- **No secrets.** No API keys, passwords, account details or tokens, even temporary ones.
- **No media.** Photos and clips never go in git; refer to them by path.
- **No personal details** beyond names and roles. Nothing about anyone's employer, health or contacts.
- **Facts that code and git don't already show.** Don't copy file contents or commit history here; link to them.
- **Short entries.** One decision per entry, a few lines each.
- Times are Eastern time, written as `2026-11-21 10:58`.
