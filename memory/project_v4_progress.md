---
name: project-v4-progress
description: Jig v4 implementation progress — what's done, what's next, phase order
metadata:
  type: project
---

Source of truth: `.context/v4-rpa-platform-proposal.md`

**Why:** Full platform build from v3 CLI-only engine → Jig UI platform. Phases A–K defined in proposal. Working one phase at a time in agreed order.

**How to apply:** Resume from "Next up" and continue down the Remaining list in order.

---

## Completed

| Phase | What was built |
|-------|---------------|
| **P0** Bug fixes | gmail_watch async fix; human_pause → v3 KV; --resume-run checkpoint skip |
| **Phase A** API Foundation | All 13 app.py API methods; --run-id flag; schedules table + CRUD in db.py |
| **Phase B** UI Shell | workspace.js, flows.js, step_card.js, live_run.js, Flows nav tab |
| **Phase F** Decision Trees | tree_view.js; Mermaid + run outcome colors; Decision Tree tab in History mode |
| **Phase E** (engine half) | engine/contracts.py; ChainValidator; BUILTIN_CONTRACTS (23 types); registry.contract; BlockDef schemas; --validate extended; get_flow_violations API; step detail contract display in workspace |
| **Phase C** Inspection | engine/errors.py (humanize_exception); StepDef.on_error_mode + StepStatus.WARNING; executor auto-screenshot on failure + non-blocking branch; get_step_result + get_screenshot API; right_panel.js (screenshot/output/retries tabs); warning step dot; History-mode step click → RightPanel |
| **Rebranding** | All "Mad Booking Agent" → "Jig"; ~/.mad_booking_agent → ~/.jig |
| **Phase G** Scheduler | engine/scheduler.py generalized (one-shot + cron + weekday + Windows); schedule_flow/unschedule_flow; schedules.js with + Flow Schedule modal |
| **Phase D** Command Palette | command_palette.js (Cmd+K, freq ranking, fuzzy search); block_library.js; search_palette() in app.py; index.html script tags |
| **Phase E** (UI half) | block_constructor.js (contract-first, "Continue to Implementation" gate); step_card.js compat connector dots; command_palette.js compat badges on block results (green=full contract, yellow=partial) |
| **Phase H** Debug Layer | executor.py `_debug_pause()` (pre-step KV check, emit debug_pause, poll continue/skip); app.py `start_debug_run/debug_continue/debug_skip`; live_run.js debug overlay (screenshot + Continue/Skip/Abort); flows.js Debug button + duration bars in history rows |
| **Phase I** Authoring Ergonomics | step_card.js: `ROUTER_TYPES`, toggle (▶/▼), `renderBranches()`; workspace.js: `_branchCollapsed` map, toggle handler, per-param rows with `{ }` suggestion dropdown (refs from prior steps' output contracts, clipboard copy) |
| **Phase J** Process Planner | engine/planner.py: PlannerSession (Playwright in background thread, expose_binding `__plannerCapture`, async `_on_capture`, confirm/discard/arm cycle, Mode B manual step + screenshot capture, `to_yaml_steps()`); planner.js: 4-phase UI (idle→capturing→parameterize→done), pending card with screenshot, confirmed row list, manual step form, parameterization pass with template/literal radio, YAML output; app.py: 7 planner methods; api.js: 8 planner wrappers; nav + CSS |

---

## Next up: Phase K — Advanced (Deferred to v4.1)

### Phase K — Advanced (Deferred to v4.1)
- Live variables pane in debug right panel
- Decision tree what-if path highlight (client-side graph walk)
- Decision tree replay mode (animate run_events)

---

## Key files reference
- Proposal: `.context/v4-rpa-platform-proposal.md`
- Packaging: `.context/v4-packaging-proposal.md`
- Engine entry: `run_flow.py`, `app.py`
- UI entry: `ui/index.html`, `ui/js/app.js`
- Contracts: `engine/contracts.py`
- Errors: `engine/errors.py`

Related: [[project_overview]], [[project_oss_name]], [[feedback_block_contract_model]]
