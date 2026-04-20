# CLAUDE.md

This file provides guidance to AI coding assistants when working with code in this repository.

> **Backup rule:** This file is gitignored. After every edit to `CLAUDE.md`, copy it to `docs/ox_instructions.md`:
> ```bash
> cp CLAUDE.md docs/ox_instructions.md
> ```

---

## CRITICAL: No Unsolicited Refactoring

**NEVER rewrite, restructure, consolidate, or "clean up" any file unless explicitly asked to refactor that specific file.**

- Every file contains deliberate, load-bearing code — assume it is intentional
- Reformatting, renaming, merging functions, or removing "seemingly unused" blocks counts as damage
- Only make the minimal targeted change needed to fulfil the request — nothing else
- If you think something could be improved, say so in a message; do NOT just do it

---

## Code Style

- **Short, minimal comments only** — do not add docstrings, comment blocks, or explanatory notes to code you did not change
- **Small focused functions** — prefer multiple small functions over one large one; do not create helpers or abstractions for one-time operations
- **No over-engineering** — do not add error handling for scenarios that cannot happen; only validate at system boundaries
- **No Unicode symbols** in code comments, UI text, alerts, or any user-facing string:
  - Instead of `✓`, use `[OK]` or `"Success:"`
  - Instead of `→`, use `->` or `"Next"`
  - Instead of `•`, use `-` in lists
  - Use icons/CSS for visual indicators, not Unicode characters

---

## File Context Rule

If the scope of a request is ambiguous — i.e. it is not obvious which files are relevant — ask before scanning or assuming. Something like: "Which files should I look at for this?"

Do not scan the entire codebase speculatively. Read only what is needed to fulfil the request.

---

## Temporary and Test Files

**NEVER create temporary or test files in the project root.**

| Location | Purpose |
|---|---|
| `docs/temp/` | Test scripts, debug outputs, API dumps, work-in-progress notes |
| `docs/archive/` | Completed task docs, migration records, historical notes |

- Both folders are in `.gitignore` — keep the repo root clean
- When a task is finished, move relevant notes from `docs/temp/` to `docs/archive/`, or delete them

---

## Secrets and Credentials

**NEVER include real secrets, tokens, or passwords in any git-tracked file.**

- Use placeholder values in tracked files: `your-secret-here`, `sk_test_your-key-here`
- Real values go in `.env.local` (gitignored) or `docs/temp/` notes (gitignored)
- This applies to: `README.md`, `CLAUDE.md`, `.env.example`, and all source files

---

## Terminal

**Use Git Bash or Linux/Raspberry Pi bash** for all terminal commands.

- This project targets Raspberry Pi — use bash-compatible syntax
- `&&` chaining, `grep`, `cat`, `ls`, and other bash commands are fine
- Use forward slashes in paths

---

## Package Manager

This is a Python project. Dependencies are managed via `pip` and listed in `requirements.txt`.

- Install: `pip install -r requirements.txt`
- Do not introduce `conda`, `poetry`, or other package managers unless explicitly asked

---

## Build Commands

```bash
# Main webcam/scanner app
python app.py

# JPG cycling app (4-panel or single panel)
python jpg_cycle_app_alt_screen_type.py

# JPG cycling app (2-screen variant)
python jpg_cycle_app_2_screen.py

# Basic JPG cycle
python jpg_cycle_app.py

# App test
python app_test.py
```

---

## Architecture Overview

<!-- Fill in per-project: stack, key directories, routing, etc. -->
