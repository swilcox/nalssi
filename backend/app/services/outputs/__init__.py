"""
Output backend implementations for distributing weather data.
"""

from app.services.outputs.base import BaseOutputBackend, WriteResult
from app.services.outputs.influxdb_backend import InfluxDBOutputBackend
from app.services.outputs.manager import OutputManager
from app.services.outputs.redis_backend import RedisOutputBackend

__all__ = [
    "BaseOutputBackend",
    "WriteResult",
    "InfluxDBOutputBackend",
    "OutputManager",
    "RedisOutputBackend",
]
