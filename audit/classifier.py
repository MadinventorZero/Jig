"""
Site classification system.
Start: one-time audit results encoded here.
Grows: add entries as new booking sources are integrated.
"""
from dataclasses import dataclass, field


@dataclass
class SiteProfile:
    site_id: str
    label: str
    url: str
    # Roadblock flags
    has_captcha: bool = False
    captcha_type: str = ""          # "recaptcha_v2" | "recaptcha_v3" | "hcaptcha" | ""
    has_js_challenge: bool = False   # Cloudflare or similar
    has_rate_limiting: bool = False
    has_browser_fingerprinting: bool = False
    has_honeypot_fields: bool = False
    requires_login: bool = False
    # Automation-friendliness
    has_public_api: bool = False
    has_ical_feed: bool = False
    form_platform: str = ""          # "civicplus" | "formstack" | "custom" | ""
    # Recommended mode
    recommended_mode: str = "high-touch"  # "high-touch" | "direct" | "api"
    notes: str = ""


KNOWN_SITES: dict[str, SiteProfile] = {
    "beverly_hills": SiteProfile(
        site_id              = "beverly_hills",
        label                = "Beverly Hills Non-Commercial Photography",
        url                  = "https://beverlyhills.org/460/Non-Commercial-Photography",
        has_captcha          = False,   # not observed; fail gracefully if detected
        has_js_challenge     = False,
        has_rate_limiting    = False,
        has_browser_fingerprinting = False,
        has_honeypot_fields  = False,
        requires_login       = False,
        has_public_api       = False,
        has_ical_feed        = False,
        form_platform        = "civicplus",
        recommended_mode     = "high-touch",
        notes                = (
            "Submissions open 14 days in advance at 9am PST. "
            "First-come first-served by inbox timestamp. "
            "Rejection email includes availability list for the next two weeks."
        ),
    ),
}


# ── Roadblock taxonomy (one-time market audit) ────────────────────────────────
# Source: common booking platform analysis as of 2026.

ROADBLOCK_MITIGATIONS: dict[str, str] = {
    "recaptcha_v2":          "Detect and pause for human solve; queue intervention email.",
    "recaptcha_v3":          "Score-based; use realistic timing and mouse movement patterns.",
    "hcaptcha":              "Similar to reCAPTCHA v2; pause for human intervention.",
    "js_challenge":          "Use Playwright with stealth plugin; avoid headless UA strings.",
    "rate_limiting":         "Add randomized delays between requests; rotate sessions.",
    "browser_fingerprinting": "Set realistic viewport, UA, and accept-language headers.",
    "honeypot_fields":       "Leave hidden fields empty; inspect DOM before filling.",
    "login_required":        "Store session cookies after manual login; refresh as needed.",
}


def classify(url: str) -> SiteProfile:
    """Look up a known site or return a generic high-touch profile."""
    for profile in KNOWN_SITES.values():
        if profile.url in url or url in profile.url:
            return profile
    return SiteProfile(
        site_id          = "unknown",
        label            = "Unknown Site",
        url              = url,
        recommended_mode = "high-touch",
        notes            = "Unclassified site — manual review recommended before automating.",
    )


def list_sites() -> list[dict]:
    return [
        {
            "site_id": p.site_id,
            "label":   p.label,
            "url":     p.url,
            "mode":    p.recommended_mode,
        }
        for p in KNOWN_SITES.values()
    ]
