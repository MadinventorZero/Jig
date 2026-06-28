"""
Vision action bridge — two distinct engines under a unified interface.

cv2 matcher  — pre-supplied PNG template, searches a live screen feed.
               Poll-able: zero marginal cost per capture, drives vision_wait_for.

LLM bridge   — no template; natural-language description sent to Claude vision.
               Discrete API call per screenshot; can scroll-and-retry but bounded hard.
               Use for one-shot discovery; avoid in tight loops.

Stitch+LLM   — scroll the full content area, stitch frames into one composite image,
               send to Claude in a single API call. Claude sees the full scrollable
               content at once. The result coordinate is remapped back to a scroll
               position + screen coordinate so the caller can scroll there and click.
               Overlap between consecutive frames is detected via cv2 template matching
               rather than trusting that scroll steps are pixel-perfect.

Hybrid path  — LLM locates once (single shot or stitched), result is cropped and saved
               as a cv2 template for all subsequent matches in the same run.
"""
from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pyautogui
import pyautogui as pag

# --- optional heavy imports; fail loudly at call time, not import time ----------
def _cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        raise RuntimeError("opencv-python is required for vision matching: pip install opencv-python")

def _mss():
    try:
        import mss
        return mss
    except ImportError:
        raise RuntimeError("mss is required for screen capture: pip install mss")

def _pil():
    from PIL import Image
    return Image

def _np():
    import numpy as np
    return np


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ScreenCapture:
    """Raw screen grab with original physical dimensions tracked."""
    data: bytes            # JPEG bytes
    phys_w: int            # physical pixels (mss native)
    phys_h: int            # physical pixels
    logical_w: int         # logical points (pyautogui coordinate space)
    logical_h: int
    scale: float           # phys / logical  (2.0 on retina)

    def to_pil(self):
        Image = _pil()
        return Image.open(io.BytesIO(self.data))


@dataclass
class MatchResult:
    """Location returned by either bridge, always in pyautogui logical coordinates."""
    x: int
    y: int
    confidence: float          # 0.0–1.0; LLM bridge maps high/medium/low → 0.9/0.7/0.5
    source: str                # "cv2" | "llm"
    bbox: Optional[tuple] = None   # ((x0,y0),(x1,y1)) in logical coords, if available
    reasoning: str = ""            # LLM bridge only


# ── Screen capture ────────────────────────────────────────────────────────────

def _capture(region: dict | None = None) -> ScreenCapture:
    """
    Capture the primary monitor (or a sub-region).
    Returns physical pixel JPEG bytes + scale factor for coordinate remapping.

    region: mss-style dict with keys top, left, width, height (physical pixels).
            None → full primary monitor.
    """
    mss = _mss()
    np  = _np()
    Image = _pil()

    logical_w, logical_h = pag.size()   # pyautogui's logical resolution

    with mss.mss() as sct:
        mon = region or sct.monitors[1]   # monitors[0] is the "all monitors" virtual; [1] is primary
        phys_w = mon["width"]
        phys_h = mon["height"]
        scale  = phys_w / logical_w      # e.g. 2.0 on retina

        raw = sct.grab(mon)
        # mss gives BGRA; convert to RGB PIL for JPEG encode
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        return ScreenCapture(
            data=buf.getvalue(),
            phys_w=phys_w,
            phys_h=phys_h,
            logical_w=logical_w,
            logical_h=logical_h,
            scale=scale,
        )


def _phys_to_logical(x: int, y: int, scale: float) -> tuple[int, int]:
    """Convert physical pixel coords (from mss/cv2) to logical coords (for pyautogui)."""
    return int(x / scale), int(y / scale)


# ── cv2 matcher ───────────────────────────────────────────────────────────────

def _cv2_find(
    template_path: str,
    capture: ScreenCapture,
    min_confidence: float = 0.85,
    grayscale: bool = True,
    multi_scale: bool = False,
    scale_range: tuple[float, float] = (0.8, 1.2),
    scale_steps: int = 5,
) -> MatchResult | None:
    """
    Run cv2.matchTemplate on a pre-captured ScreenCapture.
    Returns a MatchResult in logical coords, or None if below threshold.

    multi_scale: try resizing the template across scale_range to handle
                 captures taken at a different DPI than the template was cropped.
    """
    cv2 = _cv2()
    np  = _np()
    Image = _pil()

    tmpl_img = cv2.imread(str(template_path))
    if tmpl_img is None:
        raise FileNotFoundError(f"Template not found: {template_path}")

    screen_pil = capture.to_pil()
    screen_arr = np.array(screen_pil)
    screen_bgr = cv2.cvtColor(screen_arr, cv2.COLOR_RGB2BGR)

    if grayscale:
        screen_search = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
        tmpl_search   = cv2.cvtColor(tmpl_img, cv2.COLOR_BGR2GRAY)
    else:
        screen_search = screen_bgr
        tmpl_search   = tmpl_img

    scales = (
        [1.0 + (scale_range[1] - 1.0) * i / (scale_steps - 1) * 2 - (scale_range[1] - scale_range[0])
         for i in range(scale_steps)]
        if multi_scale else [1.0]
    )

    best_val   = -1.0
    best_loc   = None
    best_tmpl  = tmpl_search

    for s in scales:
        if s != 1.0:
            h, w = tmpl_search.shape[:2]
            t = cv2.resize(tmpl_search, (int(w * s), int(h * s)))
        else:
            t = tmpl_search

        if t.shape[0] > screen_search.shape[0] or t.shape[1] > screen_search.shape[1]:
            continue

        result = cv2.matchTemplate(screen_search, t, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val  = max_val
            best_loc  = max_loc
            best_tmpl = t

    if best_val < min_confidence or best_loc is None:
        return None

    th, tw = best_tmpl.shape[:2]
    # Center in physical coords
    cx_phys = best_loc[0] + tw // 2
    cy_phys = best_loc[1] + th // 2
    # Bounding box in physical coords
    tl_phys = best_loc
    br_phys = (best_loc[0] + tw, best_loc[1] + th)

    cx, cy  = _phys_to_logical(cx_phys, cy_phys, capture.scale)
    tl      = _phys_to_logical(*tl_phys, capture.scale)
    br      = _phys_to_logical(*br_phys, capture.scale)

    return MatchResult(x=cx, y=cy, confidence=float(best_val), source="cv2", bbox=(tl, br))


# ── Public cv2 actions ────────────────────────────────────────────────────────

def vision_find(
    template_path: str,
    min_confidence: float = 0.85,
    region: dict | None = None,
    grayscale: bool = True,
    multi_scale: bool = False,
) -> MatchResult | None:
    """Single-shot: capture screen, find template, return match or None."""
    cap = _capture(region)
    return _cv2_find(template_path, cap, min_confidence, grayscale, multi_scale)


def vision_wait_for(
    template_path: str,
    timeout: float = 30.0,
    poll_interval: float = 0.5,
    min_confidence: float = 0.85,
    region: dict | None = None,
) -> MatchResult | None:
    """
    Poll the screen until template appears or timeout.
    Uses cv2 — poll-able at near-zero cost. Do NOT use the LLM bridge for this.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cap    = _capture(region)
        result = _cv2_find(template_path, cap, min_confidence)
        if result:
            return result
        remaining = deadline - time.monotonic()
        time.sleep(min(poll_interval, max(remaining, 0)))
    return None


def vision_find_with_scroll(
    template_path: str,
    scroll_direction: str = "down",   # "down" | "up" | "right" | "left"
    scroll_amount: int = 300,         # pixels per scroll step
    max_scrolls: int = 8,
    settle_delay: float = 0.35,       # seconds to wait after scroll
    min_confidence: float = 0.85,
    region: dict | None = None,
) -> MatchResult | None:
    """
    Scroll incrementally, taking a fresh screenshot at each position.
    Returns the first match found, or None after exhausting scroll budget.
    """
    directions = {
        "down":  (0, -scroll_amount),
        "up":    (0,  scroll_amount),
        "right": (-scroll_amount, 0),
        "left":  ( scroll_amount, 0),
    }
    dx, dy = directions.get(scroll_direction, (0, -scroll_amount))

    for i in range(max_scrolls + 1):
        cap    = _capture(region)
        result = _cv2_find(template_path, cap, min_confidence)
        if result:
            return result
        if i < max_scrolls:
            pag.scroll(dy)
            if dx:
                pag.hscroll(dx)
            time.sleep(settle_delay)
    return None


def vision_assert(
    template_path: str,
    min_confidence: float = 0.85,
    region: dict | None = None,
    message: str = "",
) -> MatchResult:
    """
    Assert template is present. Raises VisionAssertError if not found.
    Use as a verification gate after a submit or navigation step.
    """
    result = vision_find(template_path, min_confidence, region)
    if result is None:
        label = message or f"Template not found: {template_path}"
        raise VisionAssertError(label)
    return result


def vision_click(
    template_path: str,
    min_confidence: float = 0.85,
    offset: tuple[int, int] = (0, 0),
    button: str = "left",
    double: bool = False,
    with_scroll: bool = False,
    max_scrolls: int = 8,
    region: dict | None = None,
) -> MatchResult:
    """Find template and click its center (+ optional offset)."""
    if with_scroll:
        result = vision_find_with_scroll(template_path, max_scrolls=max_scrolls, min_confidence=min_confidence, region=region)
    else:
        result = vision_find(template_path, min_confidence, region)
    if result is None:
        raise VisionNotFoundError(f"Cannot click — template not found: {template_path}")
    x, y = result.x + offset[0], result.y + offset[1]
    if double:
        pag.doubleClick(x, y, button=button)
    else:
        pag.click(x, y, button=button)
    return result


def vision_type(
    template_path: str,
    text: str,
    min_confidence: float = 0.85,
    clear_first: bool = True,
    interval: float = 0.03,
    region: dict | None = None,
) -> MatchResult:
    """Find template, click to focus, optionally clear, then type."""
    result = vision_click(template_path, min_confidence, region=region)
    if clear_first:
        pag.hotkey("command", "a")
        pag.press("delete")
    pag.typewrite(text, interval=interval)
    return result


def vision_extract(
    region_box: tuple[int, int, int, int],  # (x, y, w, h) in logical coords
    lang: str = "eng",
) -> str:
    """
    OCR a screen region. Returns extracted text.
    region_box: (left, top, width, height) in logical pyautogui coordinates.
    """
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError("pytesseract is required for vision_extract: pip install pytesseract")

    Image = _pil()
    np    = _np()

    cap = _capture()
    pil = cap.to_pil()

    # Scale region from logical → physical for cropping into the physical capture
    s = cap.scale
    x, y, w, h = region_box
    crop = pil.crop((int(x * s), int(y * s), int((x + w) * s), int((y + h) * s)))
    return pytesseract.image_to_string(crop, lang=lang).strip()


def vision_screenshot(save_to: str | None = None, region: dict | None = None) -> ScreenCapture:
    """Capture the screen and optionally save as JPEG. Returns ScreenCapture."""
    cap = _capture(region)
    if save_to:
        Path(save_to).parent.mkdir(parents=True, exist_ok=True)
        Path(save_to).write_bytes(cap.data)
    return cap


# ── Exceptions ────────────────────────────────────────────────────────────────

class VisionNotFoundError(RuntimeError):
    pass

class VisionAssertError(RuntimeError):
    pass


# ── Scroll-and-stitch ─────────────────────────────────────────────────────────

@dataclass
class FrameRecord:
    """One captured scroll position, stored in physical pixels."""
    capture: ScreenCapture
    composite_y: int        # y-offset of this frame's top in the final composite (physical px)
    new_content_h: int      # how many physical rows of new content this frame contributes
    scroll_logical: int     # cumulative logical scroll distance from the start position
                            # (negative = scrolled down; matches pyautogui scroll direction)


@dataclass
class StitchedCapture:
    """
    A vertically stitched composite of multiple scroll positions.

    composite_data  — JPEG bytes of the full composite image (may be resized for Claude)
    composite_w     — width of the composite in physical pixels (before any resize)
    composite_h     — height of the composite in physical pixels (before any resize)
    frames          — ordered list of FrameRecord, one per captured scroll position
    scale           — physical/logical pixel ratio (same as ScreenCapture.scale)
    sent_w / sent_h — dimensions of the image actually sent to Claude (may differ if resized)

    Use remap_to_screen() to convert Claude's percentage coordinates back to
    a (scroll_logical, screen_x, screen_y) tuple.
    """
    composite_data: bytes
    composite_w: int
    composite_h: int
    frames: list[FrameRecord]
    scale: float
    sent_w: int
    sent_h: int

    def remap_to_screen(self, x_pct: float, y_pct: float) -> tuple[int, int, int]:
        """
        Map Claude's percentage coordinates in the sent image back to screen coords.

        Returns (scroll_logical, screen_x_logical, screen_y_logical) where:
          scroll_logical  — how many total logical pixels to scroll from the start
                            position before clicking (negative = scroll down)
          screen_x/y      — pyautogui logical coordinates to click at

        Caller should:
          1. Scroll back to the start position (or track current position)
          2. pyautogui.scroll(scroll_logical)  [already negative for downward scroll]
          3. pyautogui.click(screen_x, screen_y)
        """
        # Map pct coords from sent (possibly resized) image → physical composite coords
        comp_x_phys = int(x_pct * self.composite_w)
        comp_y_phys = int(y_pct * self.composite_h)

        # Find which frame this y falls in
        frame = self.frames[0]
        for fr in self.frames:
            if fr.composite_y <= comp_y_phys:
                frame = fr
            else:
                break

        # y offset within that frame (physical pixels from frame top)
        local_y_phys = comp_y_phys - frame.composite_y

        # Convert to logical screen coordinates
        screen_x = int(comp_x_phys / self.scale)
        screen_y = int(local_y_phys / self.scale)

        return frame.scroll_logical, screen_x, screen_y


# ── Overlap detection ─────────────────────────────────────────────────────────

def _detect_frame_overlap(
    prev_arr: "np.ndarray",
    curr_arr: "np.ndarray",
    strip_h: int = 80,
    min_confidence: float = 0.92,
) -> int | None:
    """
    Find where the bottom strip of prev_arr appears in curr_arr using template matching.

    Returns the number of NEW physical-pixel rows contributed by curr_arr
    (i.e., the rows in curr_arr that are not present in prev_arr), or None
    if overlap could not be detected confidently.

    How it works:
      - Strip = bottom `strip_h` rows of prev_arr
      - Search for strip in the top half of curr_arr
      - If found at curr_arr row match_y, then rows [match_y + strip_h :] are new content
    """
    cv2 = _cv2()
    np  = _np()

    h = curr_arr.shape[0]

    # Work in grayscale — faster and more robust to minor color drift between frames
    prev_gray = cv2.cvtColor(prev_arr, cv2.COLOR_RGB2GRAY)
    curr_gray = cv2.cvtColor(curr_arr, cv2.COLOR_RGB2GRAY)

    strip = prev_gray[- strip_h:, :]

    # Only search the top half of curr — the strip must be near the top if there's overlap
    search_region = curr_gray[: h // 2 + strip_h, :]

    if strip.shape[1] != search_region.shape[1]:
        return None  # width mismatch; can't match
    if strip.shape[0] >= search_region.shape[0]:
        return None  # strip taller than search region

    result = cv2.matchTemplate(search_region, strip, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < min_confidence:
        return None  # overlap not detected reliably — caller falls back to fixed step

    match_y = max_loc[1]
    new_content_start = match_y + strip_h
    new_rows = h - new_content_start
    return max(0, new_rows)


def _frames_are_identical(
    prev_arr: "np.ndarray",
    curr_arr: "np.ndarray",
    threshold: float = 0.997,
) -> bool:
    """Return True if two frames are nearly identical (scroll end reached)."""
    cv2 = _cv2()
    np  = _np()

    prev_g = cv2.cvtColor(prev_arr, cv2.COLOR_RGB2GRAY).astype(np.float32)
    curr_g = cv2.cvtColor(curr_arr, cv2.COLOR_RGB2GRAY).astype(np.float32)

    # Normalized cross-correlation of the full frames
    result = cv2.matchTemplate(prev_g, curr_g, cv2.TM_CCOEFF_NORMED)
    return float(result[0][0]) >= threshold


# ── Public stitch function ────────────────────────────────────────────────────

def vision_stitch_scroll(
    scroll_direction: str = "down",
    scroll_step_logical: int = 400,   # logical pixels to scroll per step
    max_frames: int = 12,
    settle_delay: float = 0.3,
    overlap_strip_h: int = 80,        # physical rows used for overlap detection
    region: dict | None = None,
    reset_to_top: bool = True,        # scroll to top before starting
    max_composite_dim: int = 8000,    # cap composite height (physical px) before resize
) -> StitchedCapture:
    """
    Scroll through content, stitch frames into a single composite image.

    Overlap between consecutive frames is detected via cv2 template matching,
    so the stitch is accurate even when scroll steps aren't pixel-perfect
    (smooth scrolling, elastic scrolling, variable-height content).

    Falls back to the requested scroll_step_logical when cv2 detection fails
    (e.g., frames with very little texture or solid-color regions).

    Returns a StitchedCapture ready to pass to LLMVisionBridge.locate_in_stitched().
    """
    np    = _np()
    cv2   = _cv2()
    Image = _pil()

    if reset_to_top:
        # Scroll to top: send a large upward scroll to normalize start position
        pag.hotkey("command", "home")
        time.sleep(0.3)

    scroll_sign = -1 if scroll_direction == "down" else 1

    # ── Capture first frame ───────────────────────────────────────────────────
    cap0   = _capture(region)
    arr0   = np.array(cap0.to_pil())   # RGB numpy (H, W, 3)
    phys_h = arr0.shape[0]
    phys_w = arr0.shape[1]

    frames: list[FrameRecord] = [
        FrameRecord(capture=cap0, composite_y=0, new_content_h=phys_h, scroll_logical=0)
    ]
    composite_rows: list[np.ndarray] = [arr0]
    composite_h_so_far = phys_h
    prev_arr = arr0
    cumulative_scroll = 0

    for _ in range(max_frames - 1):
        # Scroll one step
        pag.scroll(scroll_sign * scroll_step_logical)
        cumulative_scroll += scroll_sign * scroll_step_logical
        time.sleep(settle_delay)

        cap_n = _capture(region)
        arr_n = np.array(cap_n.to_pil())

        # Detect scroll end: if frames are nearly identical, we've hit the boundary
        if _frames_are_identical(prev_arr, arr_n):
            break

        # Detect overlap via cv2 to find how many rows are genuinely new
        new_rows = _detect_frame_overlap(
            prev_arr, arr_n,
            strip_h=overlap_strip_h,
        )

        if new_rows is None:
            # cv2 couldn't detect overlap — estimate from requested scroll step
            # scale from logical pixels to physical pixels
            scale = cap_n.scale
            new_rows = min(int(scroll_step_logical * scale), phys_h)

        if new_rows <= 0:
            break  # nothing new; content didn't advance

        # Slice only the new content from the bottom of this frame
        new_content = arr_n[phys_h - new_rows:, :]

        frame_rec = FrameRecord(
            capture=cap_n,
            composite_y=composite_h_so_far,
            new_content_h=new_rows,
            scroll_logical=cumulative_scroll,
        )
        frames.append(frame_rec)
        composite_rows.append(new_content)
        composite_h_so_far += new_rows
        prev_arr = arr_n

        if composite_h_so_far >= max_composite_dim:
            break

    # ── Build composite ───────────────────────────────────────────────────────
    composite_arr = np.vstack(composite_rows)
    composite_pil = Image.fromarray(composite_arr, "RGB")
    true_w, true_h = composite_pil.size   # physical pixels

    # Resize for Claude if needed (keep aspect ratio, cap longest dimension)
    sent_pil = composite_pil
    MAX_DIM  = LLMVisionBridge.MAX_DIM
    if max(sent_pil.size) > MAX_DIM:
        sent_pil = sent_pil.copy()
        sent_pil.thumbnail((MAX_DIM, MAX_DIM * 4), Image.LANCZOS)
        # Note: thumbnail respects aspect ratio but won't exceed either dimension.
        # MAX_DIM * 4 on height allows tall composites to reach MAX_DIM width while
        # keeping their full height (Claude supports tall images).

    buf = io.BytesIO()
    sent_pil.save(buf, "JPEG", quality=80)

    return StitchedCapture(
        composite_data=buf.getvalue(),
        composite_w=true_w,
        composite_h=true_h,
        frames=frames,
        scale=frames[0].capture.scale,
        sent_w=sent_pil.width,
        sent_h=sent_pil.height,
    )


# ── LLM vision bridge ─────────────────────────────────────────────────────────
# Kept in a separate class so it's explicit at the call site that an API call is made.
# Do NOT use this inside poll loops — use cv2 bridge for anything that repeats.

@dataclass
class LLMLocationResult:
    x: int
    y: int
    confidence: str          # "high" | "medium" | "low"
    reasoning: str
    screenshot: ScreenCapture = field(repr=False)


_CONFIDENCE_MAP = {"high": 0.9, "medium": 0.7, "low": 0.5}

_LOCATE_TOOL = {
    "name": "report_element_location",
    "description": "Report the pixel location of the described UI element in the screenshot",
    "input_schema": {
        "type": "object",
        "properties": {
            "found": {
                "type": "boolean",
                "description": "Whether the described element is visible in the screenshot"
            },
            "x_pct": {
                "type": "number",
                "description": "Horizontal center of the element as a fraction of image width (0.0 = left edge, 1.0 = right edge)"
            },
            "y_pct": {
                "type": "number",
                "description": "Vertical center of the element as a fraction of image height (0.0 = top, 1.0 = bottom)"
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "How confident you are in this location"
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of what you found and why"
            },
        },
        "required": ["found"],
    },
}


class LLMVisionBridge:
    """
    Locates UI elements using Claude vision when no template is available.

    Each call = one API request. Scroll-and-retry is supported but bounded.
    For poll-based waiting, use the cv2 bridge (vision_wait_for) instead.

    Hybrid pattern: call locate_and_save_template() to discover the element once
    and persist a cv2 template crop for all subsequent runs.
    """

    # Claude's recommended max image dimension to keep within message limits
    MAX_DIM = 1568

    def __init__(self, client, model: str = "claude-sonnet-4-6"):
        self._client = client
        self._model  = model

    def _prepare_image(self, cap: ScreenCapture) -> tuple[str, int, int]:
        """
        Resize capture if oversized, return (base64_jpeg, original_phys_w, original_phys_h).
        We resize only for sending to Claude; we keep original dims to remap coords.
        """
        Image = _pil()
        img = cap.to_pil()
        orig_w, orig_h = img.size   # physical pixels

        if max(img.size) > self.MAX_DIM:
            img = img.copy()
            img.thumbnail((self.MAX_DIM, self.MAX_DIM), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        b64 = base64.standard_b64encode(buf.getvalue()).decode()
        return b64, orig_w, orig_h

    def locate(
        self,
        description: str,
        context: str = "",
        capture: ScreenCapture | None = None,
        region: dict | None = None,
    ) -> LLMLocationResult | None:
        """
        Ask Claude to find an element by natural-language description.
        Returns logical (pyautogui) coordinates, or None if not found.

        capture: pass a pre-taken ScreenCapture to avoid a second grab.
        """
        if capture is None:
            capture = _capture(region)

        b64, orig_phys_w, orig_phys_h = self._prepare_image(capture)

        prompt_parts = []
        if context:
            prompt_parts.append(f"Context: {context}")
        prompt_parts.append(
            f"Find this element in the screenshot: {description}\n"
            f"The screenshot represents a screen of {capture.logical_w}x{capture.logical_h} logical pixels "
            f"(physical resolution: {orig_phys_w}x{orig_phys_h}).\n"
            "Report its center position as fractions (0.0–1.0) of the image dimensions. "
            "Use the report_element_location tool."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            temperature=0,
            tools=[_LOCATE_TOOL],
            tool_choice={"type": "any"},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                    },
                    {"type": "text", "text": "\n".join(prompt_parts)},
                ],
            }],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "report_element_location":
                data = block.input
                if not data.get("found"):
                    return None
                # Percentages are relative to the physical image dimensions sent.
                # Map back to logical pyautogui coordinates via original physical dims.
                x_phys = int(data["x_pct"] * orig_phys_w)
                y_phys = int(data["y_pct"] * orig_phys_h)
                lx, ly = _phys_to_logical(x_phys, y_phys, capture.scale)
                return LLMLocationResult(
                    x=lx,
                    y=ly,
                    confidence=data.get("confidence", "medium"),
                    reasoning=data.get("reasoning", ""),
                    screenshot=capture,
                )
        return None

    def locate_with_scroll(
        self,
        description: str,
        context: str = "",
        scroll_direction: str = "down",
        scroll_amount: int = 400,
        max_scrolls: int = 4,
        settle_delay: float = 0.5,
        region: dict | None = None,
    ) -> LLMLocationResult | None:
        """
        Scroll and retry with Claude if not found. API cost = max_scrolls + 1 calls max.
        Keep max_scrolls low (default 4) — this is expensive relative to cv2 scrolling.
        """
        directions = {"down": -scroll_amount, "up": scroll_amount}
        dy = directions.get(scroll_direction, -scroll_amount)

        for i in range(max_scrolls + 1):
            cap    = _capture(region)
            result = self.locate(description, context, capture=cap)
            if result:
                return result
            if i < max_scrolls:
                pag.scroll(dy)
                time.sleep(settle_delay)
        return None

    def click(
        self,
        description: str,
        context: str = "",
        offset: tuple[int, int] = (0, 0),
        button: str = "left",
        double: bool = False,
        with_scroll: bool = False,
        max_scrolls: int = 4,
    ) -> LLMLocationResult:
        """Locate by description and click. Raises VisionNotFoundError if not found."""
        if with_scroll:
            result = self.locate_with_scroll(description, context, max_scrolls=max_scrolls)
        else:
            result = self.locate(description, context)
        if result is None:
            raise VisionNotFoundError(f"LLM bridge could not locate: {description}")
        x, y = result.x + offset[0], result.y + offset[1]
        if double:
            pag.doubleClick(x, y, button=button)
        else:
            pag.click(x, y, button=button)
        return result

    def locate_in_stitched(
        self,
        description: str,
        stitched: StitchedCapture,
        context: str = "",
        scroll_back_first: bool = True,
    ) -> LLMLocationResult | None:
        """
        Send a pre-built StitchedCapture to Claude as a single API call.

        Claude sees the full scrollable content at once — one call regardless of
        how many frames were stitched.  Returns a LLMLocationResult whose (x, y)
        are ready-to-use pyautogui logical coordinates after the caller scrolls
        to the correct position.

        scroll_back_first: if True, scroll back to the start position before
        returning so the caller starts from a known state.

        Usage:
            stitched = vision_stitch_scroll()
            result   = bridge.locate_in_stitched("blue Submit button", stitched)
            if result:
                pyautogui.scroll(result.scroll_needed)
                pyautogui.click(result.x, result.y)
        """
        b64  = base64.standard_b64encode(stitched.composite_data).decode()
        sent_w, sent_h = stitched.sent_w, stitched.sent_h

        prompt_parts = []
        if context:
            prompt_parts.append(f"Context: {context}")
        prompt_parts.append(
            f"This is a vertically stitched composite screenshot of scrollable content "
            f"({sent_w}×{sent_h} px as displayed, representing "
            f"{stitched.composite_w}×{stitched.composite_h} physical pixels across "
            f"{len(stitched.frames)} scroll positions).\n"
            f"Find this element: {description}\n"
            "Report its center as fractions of THIS image's dimensions (0.0–1.0). "
            "Use the report_element_location tool."
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            temperature=0,
            tools=[_LOCATE_TOOL],
            tool_choice={"type": "any"},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                    },
                    {"type": "text", "text": "\n".join(prompt_parts)},
                ],
            }],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "report_element_location":
                data = block.input
                if not data.get("found"):
                    return None

                x_pct = data.get("x_pct", 0.5)
                y_pct = data.get("y_pct", 0.5)

                # thumbnail() is a proportional resize, so percentage coords in the
                # sent image are identical to percentage coords in the true composite.
                # Pass them directly — no adjustment needed.
                scroll_logical, screen_x, screen_y = stitched.remap_to_screen(
                    x_pct, y_pct
                )

                if scroll_back_first:
                    # Return to start position: undo all cumulative scroll
                    total_scroll = stitched.frames[-1].scroll_logical
                    if total_scroll != 0:
                        pag.scroll(-total_scroll)
                        time.sleep(0.3)

                result = LLMLocationResult(
                    x=screen_x,
                    y=screen_y,
                    confidence=data.get("confidence", "medium"),
                    reasoning=data.get("reasoning", ""),
                    screenshot=stitched.frames[0].capture,
                )
                result.scroll_needed = scroll_logical   # type: ignore[attr-defined]
                return result
        return None

    def stitch_and_locate(
        self,
        description: str,
        context: str = "",
        scroll_direction: str = "down",
        scroll_step_logical: int = 400,
        max_frames: int = 12,
        region: dict | None = None,
        save_composite_to: str | None = None,
    ) -> LLMLocationResult | None:
        """
        Convenience wrapper: stitch the screen then locate in one call.

        Optionally saves the composite image for debugging.
        After locating, the caller still needs to scroll and click:

            result = bridge.stitch_and_locate("Submit button")
            if result:
                pyautogui.scroll(result.scroll_needed)
                pyautogui.click(result.x, result.y)
        """
        stitched = vision_stitch_scroll(
            scroll_direction=scroll_direction,
            scroll_step_logical=scroll_step_logical,
            max_frames=max_frames,
            region=region,
        )
        if save_composite_to:
            Path(save_composite_to).parent.mkdir(parents=True, exist_ok=True)
            Path(save_composite_to).write_bytes(stitched.composite_data)

        return self.locate_in_stitched(description, stitched, context)

    def locate_and_save_template(
        self,
        description: str,
        save_path: str,
        padding: int = 12,
        context: str = "",
    ) -> LLMLocationResult | None:
        """
        Hybrid discovery: locate with LLM, crop the region, save as a cv2 template PNG.

        After calling this once, subsequent runs can use vision_find(save_path) with
        zero API cost. The saved template is centered on the located coordinates with
        `padding` pixels of margin on each side.
        """
        Image = _pil()
        cap    = _capture()
        result = self.locate(description, context, capture=cap)
        if result is None:
            return None

        # Crop a region around the located point from the physical capture image
        pil     = cap.to_pil()
        s       = cap.scale
        cx_phys = int(result.x * s)
        cy_phys = int(result.y * s)
        pad_phys = int(padding * s)

        # Estimate a reasonable crop size if bbox is not available (40×40 logical px)
        half_w = int(20 * s) + pad_phys
        half_h = int(20 * s) + pad_phys

        crop = pil.crop((
            max(0, cx_phys - half_w),
            max(0, cy_phys - half_h),
            min(cap.phys_w, cx_phys + half_w),
            min(cap.phys_h, cy_phys + half_h),
        ))

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        crop.save(save_path, "PNG")
        return result


# ── Action registry wrappers ─────────────────────────────────────────────────
# All vision functions are synchronous; wrap with asyncio.to_thread.

def register(registry) -> None:
    import asyncio

    async def _vision_find(ctx, params):
        r = await asyncio.to_thread(
            vision_find,
            params["template_path"],
            params.get("min_confidence", 0.85),
            params.get("region"),
            params.get("grayscale", True),
            params.get("multi_scale", False),
        )
        if r is None:
            return {"found": False, "x": None, "y": None, "confidence": 0,
                    "choice": "not_found"}
        return {"found": True, "x": r.x, "y": r.y, "confidence": r.confidence,
                "choice": "found"}

    async def _vision_click(ctx, params):
        r = await asyncio.to_thread(
            vision_click,
            params["template_path"],
            params.get("min_confidence", 0.85),
            tuple(params.get("offset", [0, 0])),
            params.get("button", "left"),
            params.get("double", False),
            params.get("with_scroll", False),
            params.get("max_scrolls", 8),
            params.get("region"),
        )
        return {"x": r.x, "y": r.y, "confidence": r.confidence, "choice": "ok"}

    async def _vision_assert(ctx, params):
        try:
            r = await asyncio.to_thread(
                vision_assert,
                params["template_path"],
                params.get("min_confidence", 0.85),
                params.get("region"),
                params.get("message", ""),
            )
            return {"found": True, "x": r.x, "y": r.y, "choice": "ok"}
        except VisionAssertError as e:
            return {"found": False, "error": str(e), "choice": "not_found"}

    async def _vision_screenshot(ctx, params):
        cap = await asyncio.to_thread(
            vision_screenshot,
            params.get("save_to"),
            params.get("region"),
        )
        return {"width": cap.logical_w, "height": cap.logical_h, "choice": "ok"}

    async def _vision_extract(ctx, params):
        text = await asyncio.to_thread(
            vision_extract,
            tuple(params["region"]),
            params.get("lang", "eng"),
        )
        return {"text": text, "ok": True, "choice": "ok"}

    registry.register("vision_find",       _vision_find,
                       "Find a cv2 template on screen")
    registry.register("vision_click",      _vision_click,
                       "Find a cv2 template and click its center")
    registry.register("vision_assert",     _vision_assert,
                       "Assert a cv2 template is present (raises on failure)")
    registry.register("vision_screenshot", _vision_screenshot,
                       "Capture and optionally save a screenshot")
    registry.register("vision_extract",    _vision_extract,
                       "OCR a screen region via pytesseract")
