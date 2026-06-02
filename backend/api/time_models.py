from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer

from core.time_utils import serialize_datetime_utc


class UTCDateTimeModel(BaseModel):
    @field_serializer("*", check_fields=False)
    def serialize_datetimes(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return serialize_datetime_utc(value)
        return value
