"""
Celery beat schedule — GPU Gross Margin Visibility.

Defines periodic tasks:
  - approved_session_closer: runs every 60s, marks APPROVED sessions as TERMINAL.
"""

beat_schedule = {
    "approved-session-closer": {
        "task": "app.tasks.close_approved_sessions",
        "schedule": 60.0,
    },
}
