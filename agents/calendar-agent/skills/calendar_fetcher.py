"""
Calendar Fetcher — Google Calendar API interactions.

Read-only. Surfaces today's events, upcoming meetings, and free time blocks.
Uses OAuth tokens managed by shared/google_auth.py.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")
from shared.google_auth import google_request

CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")


def get_today_events() -> list[dict]:
    """Get all events for today."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    return _fetch_events(start_of_day, end_of_day)


def get_upcoming_events(hours: int = 48, max_results: int = 20) -> list[dict]:
    """Get upcoming events for the next N hours."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours)

    return _fetch_events(now, end, max_results=max_results)


def get_free_slots(date: str | None = None, min_duration_minutes: int = 30) -> list[dict]:
    """Find free time slots in the day (gaps between meetings).

    Args:
        date: ISO date string (YYYY-MM-DD). Defaults to today.
        min_duration_minutes: Minimum free block size to report.
    """
    if date:
        day_start = datetime.fromisoformat(f"{date}T00:00:00+00:00")
    else:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Working hours: 8 AM to 6 PM (adjust via env)
    work_start_hour = int(os.getenv("WORK_START_HOUR", "8"))
    work_end_hour = int(os.getenv("WORK_END_HOUR", "18"))

    work_start = day_start.replace(hour=work_start_hour)
    work_end = day_start.replace(hour=work_end_hour)

    events = _fetch_events(work_start, work_end)
    if not events:
        return [{"start": work_start.isoformat(), "end": work_end.isoformat(),
                 "duration_minutes": (work_end_hour - work_start_hour) * 60}]

    # Sort events by start time
    busy_periods = []
    for e in events:
        start_str = e.get("start_time", "")
        end_str = e.get("end_time", "")
        if start_str and end_str:
            try:
                s = datetime.fromisoformat(start_str)
                en = datetime.fromisoformat(end_str)
                busy_periods.append((s, en))
            except ValueError:
                continue

    busy_periods.sort(key=lambda x: x[0])

    # Find gaps
    free_slots = []
    current = work_start
    for busy_start, busy_end in busy_periods:
        if busy_start > current:
            gap_minutes = (busy_start - current).total_seconds() / 60
            if gap_minutes >= min_duration_minutes:
                free_slots.append({
                    "start": current.isoformat(),
                    "end": busy_start.isoformat(),
                    "duration_minutes": int(gap_minutes),
                })
        current = max(current, busy_end)

    # Check gap after last meeting
    if current < work_end:
        gap_minutes = (work_end - current).total_seconds() / 60
        if gap_minutes >= min_duration_minutes:
            free_slots.append({
                "start": current.isoformat(),
                "end": work_end.isoformat(),
                "duration_minutes": int(gap_minutes),
            })

    return free_slots


def _fetch_events(
    time_min: datetime, time_max: datetime, max_results: int = 50,
) -> list[dict]:
    """Fetch events from Google Calendar API."""
    data = google_request(
        "GET",
        f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events",
        params={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        },
    )

    if "error" in data:
        return []

    events = []
    for item in data.get("items", []):
        start = item.get("start", {})
        end = item.get("end", {})

        events.append({
            "id": item.get("id", ""),
            "summary": item.get("summary", "No title"),
            "start_time": start.get("dateTime", start.get("date", "")),
            "end_time": end.get("dateTime", end.get("date", "")),
            "location": item.get("location", ""),
            "organizer": item.get("organizer", {}).get("email", ""),
            "status": item.get("status", "confirmed"),
            "attendees": [
                a.get("email", "") for a in item.get("attendees", [])[:10]
            ],
            "hangout_link": item.get("hangoutLink", ""),
            "is_all_day": "date" in start and "dateTime" not in start,
        })

    return events
