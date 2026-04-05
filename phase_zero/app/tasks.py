from app.celery_app import celery_app

@celery_app.task
def approved_session_closer():
    pass