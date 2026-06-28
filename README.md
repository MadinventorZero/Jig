# Jig

**Local-First, LLM-Enabled RPA. Your workflow. Your rules. Your way.**

Jig is a desktop automation platform for engineers who already know what they're automating. Define flows in YAML, compose typed block contracts, and let the pipeline handle browser automation, email, HTTP, file ops, and LLM-assisted decisions — all on your machine, no cloud required.

---

## How it works

Flows are YAML files. Steps are typed contracts — each block declares what it takes in and what it produces. The pipeline validates the chain at design time so mismatches surface before a single line runs.

```yaml
steps:
  - step_id: navigate
    type: browser_navigate
    params:
      url: "{{ flow.context.target_url }}"

  - step_id: fill_form
    type: block
    block: fill_form_fields

  - step_id: decide
    type: llm_decide
    prompt: "Did the form submission succeed? Look for a confirmation message."
    on_choice:
      yes: watch_email
      no:  retry_navigate
```

Steps are flat. Branches are explicit. LLM decision points (`llm_decide`) are first-class step types — not bolted on.

---

## What runs

- **Browser** — navigate, click, type, screenshot, vision-based element detection (Playwright)
- **Email** — Gmail watch, parse, reply (Google API + OAuth)
- **HTTP** — arbitrary API calls
- **Scripts** — run local scripts mid-flow
- **LLM decisions** — structured yes/no/multiple-choice at any step (Claude)
- **Human pause** — halt and wait for your input, then resume

---

## Scheduling

Flows run on-demand or on a schedule. Schedules are managed via launchd (macOS) or Task Scheduler (Windows) — they survive reboots and don't require the app to be open.

---

## Requirements

- macOS 13+ or Windows 10+
- Python 3.13+ (installed automatically by `setup.command` on macOS)
- A Gmail account with a Google Cloud OAuth credential ([setup guide](docs/gmail-setup.md))

---

## Setup

**macOS:** Double-click `setup.command` in Finder or run it in Terminal.

**Windows:** Double-click `setup.bat` (requires Python 3.13+ already installed).

Setup creates a `.venv`, installs all dependencies, downloads Chromium, and generates icon assets. Run once per machine. After that, see [docs/running.md](docs/running.md).

---

## Running

```bash
python run.py                              # dev — terminal stays open
make alias && open "dist/Jig.app"          # alias bundle — menu bar app, live code
make bundle-mac                            # production macOS bundle
make bundle-win                            # production Windows bundle
```

Full details: [docs/running.md](docs/running.md) | [docs/bundling.md](docs/bundling.md)

---

## Project structure

```
Jig/
├── app.py                  # pywebview entry point and Python/JS API bridge
├── run_flow.py             # YAML flow runner
├── run.py                  # launcher
├── setup.command           # one-time setup (macOS)
│
├── engine/
│   ├── actions/            # step handlers — browser, email, llm, flow control
│   ├── browser.py          # Playwright session with human-emulation helpers
│   ├── db.py               # SQLite store — runs, events, schedules, KV
│   ├── executor.py         # step executor with contract enforcement
│   ├── pipeline.py         # async pipeline runner
│   ├── scheduler.py        # launchd plist writer and fire-time calculator
│   └── v3_models.py        # FlowDef, StepDef, BlockDef dataclasses
│
├── sources/
│   ├── flows/              # YAML flow definitions
│   └── blocks/             # reusable typed block definitions
│
├── ui/
│   ├── index.html
│   └── js/
│       ├── views/          # flows, schedules, run history, live run
│       └── components/     # step cards, right panel, command palette
│
└── data/                   # runtime data (gitignored)
    ├── profiles/
    ├── screenshots/
    └── credentials/
```

---

## Data and privacy

Everything stays local. Nothing leaves your machine.

| Location | Contents |
|---|---|
| `data/` | Profiles, run history, logs, debug screenshots |
| `~/.jig/` | Gmail OAuth credentials |

Gmail credentials are stored outside the project directory so they can't be accidentally committed. Add `data/` to `.gitignore`.
