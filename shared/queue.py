"""Celery app: the job queue connecting the workers.

Each worker listens on its own queue:
  ingestion  -> preprocess + index policy, FHIR history, claim
  agent      -> build the audit report
  evaluator  -> check the report

Start one worker per queue (see Makefile: make workers).
"""
from celery import Celery

from shared.config import REDIS_URL

app = Celery("mediaudit", broker=REDIS_URL, backend=REDIS_URL,
             include=["ingestion.tasks", "agent.tasks", "evaluator.tasks"])

app.conf.update(
    task_routes={
        "ingestion.*": {"queue": "ingestion"},
        "agent.*": {"queue": "agent"},
        "evaluator.*": {"queue": "evaluator"},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,            # a task that crashes mid-way is retried, not lost
    worker_prefetch_multiplier=1,   # take one job at a time
    result_expires=24 * 3600,
)
