"""Cron policy for disk health checks."""

from diskha.interface.CronSchedule import CronSchedule
from diskha.interface.HealthConfiguration import HealthConfiguration


class HealthSchedule(CronSchedule):
    COMMENT = "disk-ha-health-check"
    CONFIG_NAME = "health.json"
    RUNNER_NAME = "disk-ha-check"
    RESULT_NAME = "health.json"
    LOG_NAME = "health.log"
    CONFIGURATION = HealthConfiguration
