from celery.schedules import crontab

beat_schedule = {
    "approved-session-closer": {
        "task": "app.tasks.approved_session_closer",
        "schedule": 60.0,
    },
}