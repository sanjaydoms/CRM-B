from datetime import datetime, timezone
import logging
import threading
import uuid
from typing import Any, Dict, Optional, List

from apps.email_service.services.email_service import EmailService
from apps.email_service.services.redis_service import RedisService

logger = logging.getLogger(__name__)

REDIS_JOB_PREFIX = "email_job:"
REDIS_QUEUE_KEY = "email_job_queue"
JOB_TTL_SECONDS = 86400 * 7  # Retain job history for 7 days


class EmailJobService:

    @classmethod
    def enqueue_job(cls, payload: Dict[str, Any], auto_trigger: bool = True) -> Dict[str, Any]:
        """Enqueues an email job into Upstash Redis for background execution.

        Returns the initial job metadata including the job_id.
        """
        job_id = str(uuid.uuid4())
        recipients = payload.get("recipients") or payload.get("recipient") or []
        if isinstance(recipients, str):
            recipients = [recipients]
        
        now_str = datetime.now(timezone.utc).isoformat()

        job_data = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now_str,
            "updated_at": now_str,
            "completed_at": None,
            "payload": {
                "subject": payload.get("subject"),
                "recipients": recipients,
                "message": payload.get("message") or payload.get("body"),
                "html_message": payload.get("html_message"),
                "send_mode": payload.get("send_mode", "bcc"),
            },
            "total_recipients": len(recipients),
            "sent_count": 0,
            "failed_count": 0,
            "failed_recipients": [],
            "error": None,
            "send_mode": payload.get("send_mode", "bcc"),
        }

        job_key = f"{REDIS_JOB_PREFIX}{job_id}"
        RedisService.set(job_key, job_data, ex=JOB_TTL_SECONDS)
        RedisService.rpush(REDIS_QUEUE_KEY, job_id)

        logger.info("Enqueued background email job %s to Redis with %d recipients", job_id, len(recipients))

        if auto_trigger:
            # Spawn a background daemon thread to process the job immediately
            thread = threading.Thread(
                target=cls._async_process_worker,
                args=(job_id,),
                daemon=True,
            )
            thread.start()

        return job_data

    @classmethod
    def _async_process_worker(cls, job_id: str) -> None:
        """Internal daemon thread worker target."""
        try:
            cls.process_job(job_id)
        except Exception:
            logger.exception("Error in background email job execution for %s", job_id)

    @classmethod
    def process_job(cls, job_id: str) -> Dict[str, Any]:
        """Processes a single email job by job_id and updates its status in Upstash Redis."""
        job_key = f"{REDIS_JOB_PREFIX}{job_id}"
        job_data = RedisService.get(job_key, parse_json=True)

        if not job_data:
            logger.error("Job %s not found in Redis", job_id)
            return {"error": "Job not found", "job_id": job_id}

        # Update status to processing
        job_data["status"] = "processing"
        job_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        RedisService.set(job_key, job_data, ex=JOB_TTL_SECONDS)

        payload = job_data.get("payload", {})
        subject = payload.get("subject", "")
        recipients = payload.get("recipients", [])
        body = payload.get("message") or payload.get("body", "")
        html_message = payload.get("html_message")
        send_mode = payload.get("send_mode", "bcc")

        result = EmailService.send_bulk_email(
            subject=subject,
            recipients=recipients,
            body=body,
            html_message=html_message,
            send_mode=send_mode,
        )

        completed_at = datetime.now(timezone.utc).isoformat()
        job_data["updated_at"] = completed_at
        job_data["completed_at"] = completed_at
        job_data["sent_count"] = result.get("sent_count", 0)
        job_data["failed_count"] = result.get("failed_count", 0)
        job_data["failed_recipients"] = result.get("failed_recipients", [])
        job_data["error"] = result.get("error")

        if result.get("success"):
            job_data["status"] = "completed"
        else:
            job_data["status"] = "failed"

        RedisService.set(job_key, job_data, ex=JOB_TTL_SECONDS)
        logger.info("Completed email job %s with status %s", job_id, job_data["status"])
        return job_data

    @classmethod
    def process_next_queued_job(cls) -> Optional[Dict[str, Any]]:
        """Pops the next job_id from the queue and processes it."""
        job_id = RedisService.lpop(REDIS_QUEUE_KEY)
        if not job_id:
            return None
        return cls.process_job(str(job_id))

    @classmethod
    def get_job_status(cls, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves current metadata and progress for a job_id from Redis."""
        job_key = f"{REDIS_JOB_PREFIX}{job_id}"
        return RedisService.get(job_key, parse_json=True)
