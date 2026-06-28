"""Process Planner — intent-intercept session recorder using Playwright."""
import asyncio
import threading
import uuid
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent

# ── Interceptor script injected into every page ──────────────────────────────

INTERCEPTOR_JS = r"""
(function() {
  var armed = true;
  window.__plannerArm = function() { armed = true; };

  // Clicks: capture + prevent state change
  document.addEventListener('click', function(evt) {
    if (!armed || !evt.isTrusted) return;
    armed = false;
    evt.preventDefault();
    evt.stopImmediatePropagation();
    _capture(evt.target, 'click', null);
  }, { capture: true });

  // Form submit: capture + prevent
  document.addEventListener('submit', function(evt) {
    if (!armed || !evt.isTrusted) return;
    armed = false;
    evt.preventDefault();
    evt.stopImmediatePropagation();
    _capture(evt.target, 'submit', null);
  }, { capture: true });

  // Select / checkbox / radio: capture + prevent
  document.addEventListener('change', function(evt) {
    if (!armed || !evt.isTrusted) return;
    var el = evt.target;
    var tag = el.tagName;
    if (tag === 'SELECT' || (tag === 'INPUT' &&
        (el.type === 'checkbox' || el.type === 'radio'))) {
      armed = false;
      evt.preventDefault();
      evt.stopImmediatePropagation();
      _capture(el, 'select', el.type === 'checkbox'
        ? (el.checked ? 'true' : 'false') : el.value);
    }
  }, { capture: true });

  // Text input: capture on blur with final value (don't prevent — user must type)
  document.addEventListener('blur', function(evt) {
    if (!armed || !evt.isTrusted) return;
    var el = evt.target;
    if ((el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && el.value) {
      armed = false;
      _capture(el, 'type', el.value);
    }
  }, { capture: true });

  function _capture(el, evtType, value) {
    window.__plannerCapture({
      event_type:   evtType,
      tag:          el.tagName,
      selector:     _bestSelector(el),
      aria_label:   el.getAttribute('aria-label') || null,
      text_content: (el.innerText || el.textContent || '').trim().slice(0, 80),
      value:        value != null ? String(value) : (el.value || null),
      placeholder:  el.getAttribute('placeholder') || null,
      input_type:   el.getAttribute('type') || null,
    });
  }

  function _bestSelector(el) {
    if (el.id) return '#' + el.id;
    var testId = el.getAttribute('data-testid');
    if (testId) return '[data-testid="' + testId + '"]';
    var aria = el.getAttribute('aria-label');
    if (aria) return '[aria-label="' + aria + '"]';
    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
    return _nthPath(el);
  }

  function _nthPath(el) {
    var parts = [];
    var node = el;
    while (node && node.tagName) {
      var tag = node.tagName.toLowerCase();
      var parent = node.parentElement;
      if (parent) {
        var siblings = Array.from(parent.children).filter(
          function(c) { return c.tagName === node.tagName; });
        if (siblings.length > 1) {
          tag += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
        }
      }
      parts.unshift(tag);
      node = node.parentElement;
      if (parts.length >= 4) break;
    }
    return parts.join(' > ');
  }
})();
"""


# ── YAML step generator ───────────────────────────────────────────────────────

def _intent_to_step(intent: dict, index: int) -> dict:
    event_type = intent.get('event_type', 'click')
    selector   = intent.get('selector', '')
    value      = intent.get('value')
    step_id    = intent.get('step_id') or f'planner_step_{index + 1}'

    if event_type == 'click':
        return {'step_id': step_id, 'type': 'browser_click',
                'params': {'selector': selector}}
    elif event_type == 'type':
        return {'step_id': step_id, 'type': 'browser_fill',
                'params': {'selector': selector, 'value': value or ''}}
    elif event_type == 'select':
        return {'step_id': step_id, 'type': 'browser_select',
                'params': {'selector': selector, 'value': value or ''}}
    elif event_type == 'submit':
        return {'step_id': step_id, 'type': 'browser_submit',
                'params': {'selector': selector}}
    else:
        return {'step_id': step_id, 'type': 'browser_click',
                'params': {'selector': selector}}


# ── PlannerSession ────────────────────────────────────────────────────────────

class PlannerSession:
    def __init__(self):
        self.session_id      = str(uuid.uuid4())
        self.intents: list[dict] = []
        self.pending: Optional[dict] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._page           = None
        self._browser        = None
        self._pw             = None
        self._ready          = threading.Event()
        self._error: Optional[Exception] = None
        self._capture_index  = 0
        self._shots_dir = ROOT / 'data' / 'planner_sessions' / self.session_id
        self._shots_dir.mkdir(parents=True, exist_ok=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start_sync(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=30)
        if self._error:
            raise self._error

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_start())
        except Exception as exc:
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        self._loop.run_forever()

    async def _async_start(self) -> None:
        from playwright.async_api import async_playwright
        self._pw      = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=False)
        ctx           = await self._browser.new_context(
            viewport={'width': 1280, 'height': 900},
        )
        self._page = await ctx.new_page()
        await self._page.expose_binding('__plannerCapture', self._on_capture)
        await self._page.add_init_script(INTERCEPTOR_JS)

    def close(self) -> None:
        if self._loop and not self._loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._async_close(), self._loop
                ).result(timeout=10)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)

    async def _async_close(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass

    # ── Capture handler (runs in session event loop) ──────────────────────────

    async def _on_capture(self, source: dict, intent: dict) -> None:
        idx = self._capture_index
        self._capture_index += 1
        shot_path = self._shots_dir / f'{idx}.png'
        try:
            shot_bytes = await self._page.screenshot(full_page=False)
            shot_path.write_bytes(shot_bytes)
            rel_path = str(shot_path.relative_to(ROOT))
        except Exception:
            rel_path = None
        intent['capture_index']    = idx
        intent['screenshot_path'] = rel_path
        self.pending = intent

    # ── Confirm / Discard ─────────────────────────────────────────────────────

    def _call_async(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=15)

    def confirm(self, capture_index: int, edits: dict = None) -> None:
        if self.pending and self.pending.get('capture_index') == capture_index:
            intent = dict(self.pending)
            if edits:
                intent.update(edits)
            intent['confirmed_index'] = len(self.intents)
            self.intents.append(intent)
            self.pending = None
        self._call_async(self._arm())

    def discard(self, capture_index: int) -> None:
        if self.pending and self.pending.get('capture_index') == capture_index:
            self.pending = None
        self._call_async(self._arm())

    async def _arm(self) -> None:
        try:
            await self._page.evaluate('window.__plannerArm()')
        except Exception:
            pass

    def add_manual(self, intent: dict) -> None:
        """Add a manually-authored intent directly (Mode B fallback)."""
        intent['capture_index']    = self._capture_index
        intent['screenshot_path'] = None
        intent['confirmed_index'] = len(self.intents)
        self._capture_index += 1
        self.intents.append(intent)

    # ── Mode B: manual screenshot ─────────────────────────────────────────────

    def capture_screenshot(self) -> str:
        return self._call_async(self._async_capture_screenshot())

    async def _async_capture_screenshot(self) -> str:
        idx       = self._capture_index
        self._capture_index += 1
        shot_path = self._shots_dir / f'manual_{idx}.png'
        shot_bytes = await self._page.screenshot(full_page=False)
        shot_path.write_bytes(shot_bytes)
        return str(shot_path.relative_to(ROOT))

    # ── State / YAML ──────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        return {
            'session_id':      self.session_id,
            'confirmed_count': len(self.intents),
            'intents':         list(self.intents),
            'pending':         dict(self.pending) if self.pending else None,
        }

    def to_yaml_steps(self) -> list[dict]:
        return [_intent_to_step(i, idx) for idx, i in enumerate(self.intents)]


# ── Session registry ──────────────────────────────────────────────────────────

_sessions: dict[str, PlannerSession] = {}


def create_session() -> PlannerSession:
    session = PlannerSession()
    session.start_sync()
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> Optional[PlannerSession]:
    return _sessions.get(session_id)


def close_session(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    if session:
        try:
            session.close()
        except Exception:
            pass
