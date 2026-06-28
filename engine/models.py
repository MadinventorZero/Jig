from dataclasses import dataclass, field
from typing import Optional


class BookingStatus:
    IDLE                 = "idle"
    RUNNING              = "running"
    SUBMITTED            = "submitted"
    REJECTED             = "rejected"
    FALLBACK_SUBMITTED   = "fallback_submitted"
    CONFIRMED            = "confirmed"
    PERMIT_GRANTED       = "permit_granted"
    INTERVENTION         = "intervention_required"
    FAILED               = "failed"
    CANCELLED            = "cancelled"


@dataclass
class BookingAttempt:
    attempt_id: str
    timestamp: str
    action: str    # "submit" | "fallback_reply" | "intervention_sent" | "intervention_resolved"
    status: str    # "success" | "failed"
    detail: str


@dataclass
class Profile:
    profile_id: str
    label: str
    # Base personal info
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone: str
    email: str
    # Site-specific fields: {site_id: {field_key: value}}
    sites: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Booking:
    booking_id: str
    profile_id: str
    site_id: str
    target_date: str           # "YYYY-MM-DD" — the permit date
    status: str                # BookingStatus constant
    created_at: str
    updated_at: str
    schedule_id: Optional[str] = None
    attempts: list = field(default_factory=list)
    gmail_thread_id: Optional[str] = None
    confirmed_date: Optional[str] = None
    confirmed_time: Optional[str] = None
    notes: str = ""


@dataclass
class Schedule:
    schedule_id: str
    label: str
    profile_id: str
    site_id: str
    target_date: str           # "YYYY-MM-DD" — the permit date to book
    fire_at: str               # ISO datetime — auto-calculated (target - 14 days at 9am PST)
    enabled: bool = False
    retry_count: int = 3
    retry_interval_seconds: int = 60
    launchd_label: Optional[str] = None
    created_at: str = ""
    last_run_at: Optional[str] = None
    last_booking_id: Optional[str] = None
