"""
Scheduled task management using APScheduler.

Manages periodic weather data collection for all enabled locations.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.services.collectors import get_collector

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Manages scheduled weather collection tasks.
    """

    def __init__(self):
        """Initialize the scheduler service."""
        self.scheduler = BackgroundScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,  # Combine missed runs into one
                "max_instances": 1,  # Only one instance of job at a time
                "misfire_grace_time": 60,  # Grace period for delayed jobs
            },
        )
        self.collector = get_collector()
        logger.info("Scheduler service initialized")

    def start(self) -> None:
        """
        Start the scheduler and add collection jobs.
        """
        if self.scheduler.running:
            logger.warning("Scheduler is already running")
            return

        # Add weather collection job (current weather + alerts)
        self.scheduler.add_job(
            func=self.collector.collect_all_sync,
            trigger=IntervalTrigger(seconds=settings.DEFAULT_COLLECTION_INTERVAL),
            id="weather_collection",
            name="Collect weather data for all locations",
            replace_existing=True,
        )

        # Add forecast collection job (separate, longer interval)
        self.scheduler.add_job(
            func=self.collector.collect_all_forecasts_sync,
            trigger=IntervalTrigger(seconds=settings.FORECAST_COLLECTION_INTERVAL),
            id="forecast_collection",
            name="Collect forecast data for all locations",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            "Scheduler started",
            extra={
                "weather_interval_seconds": settings.DEFAULT_COLLECTION_INTERVAL,
                "forecast_interval_seconds": settings.FORECAST_COLLECTION_INTERVAL,
            },
        )

        # Run first collection immediately
        logger.info("Running initial weather collection")
        try:
            self.collector.collect_all_sync()
        except Exception as e:
            logger.error(
                "Initial weather collection failed",
                extra={"error": str(e)},
                exc_info=True,
            )

        logger.info("Running initial forecast collection")
        try:
            self.collector.collect_all_forecasts_sync()
        except Exception as e:
            logger.error(
                "Initial forecast collection failed",
                extra={"error": str(e)},
                exc_info=True,
            )

    def shutdown(self) -> None:
        """
        Shutdown the scheduler gracefully.
        """
        if not self.scheduler.running:
            logger.warning("Scheduler is not running")
            return

        logger.info("Shutting down scheduler")
        self.scheduler.shutdown(wait=True)
        logger.info("Scheduler shut down successfully")

    def get_jobs(self) -> list:
        """
        Get list of scheduled jobs.

        Returns:
            List of job information
        """
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat()
                if job.next_run_time
                else None,
            }
            for job in self.scheduler.get_jobs()
        ]


# Global scheduler instance
_scheduler: SchedulerService | None = None


def get_scheduler() -> SchedulerService:
    """
    Get or create the global scheduler instance.

    Returns:
        SchedulerService instance
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler
