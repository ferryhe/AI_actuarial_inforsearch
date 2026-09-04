from __future__ import annotations

import re
from dataclasses import dataclass

SUPPORTED_SCHEDULE_TIMEZONES = frozenset({"UTC", "Asia/Shanghai"})

_CANONICAL_ROLLING_RE = re.compile(r"every ([1-9]\d*) (minutes|hours)")
_CANONICAL_FIXED_RE = re.compile(r"(daily|weekly) at ([01]\d|2[0-3]):([0-5]\d)")
_LEGACY_FIXED_RE = re.compile(r"(daily|weekly) at (\d{1,2}):(\d{1,2})")


class SchedulePresetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SchedulePreset:
    interval: str
    frequency: str
    quantity: int
    at_time: str | None
    timezone: str | None
    legacy: bool = False

    @property
    def effective_label(self) -> str:
        if self.frequency == "daily":
            return f"daily at {self.at_time}"
        if self.frequency == "weekly":
            return f"weekly on monday at {self.at_time}"
        return f"every {self.quantity} {self.frequency}"


def _timezone_value(value: object) -> str | None:
    return None if value is None else str(value)


def _validate_timezone(timezone_name: str | None) -> None:
    if timezone_name is not None and timezone_name not in SUPPORTED_SCHEDULE_TIMEZONES:
        raise SchedulePresetError("Timezone must be exactly UTC or Asia/Shanghai")


def effective_task_timezone(
    task_type: object, interval: object, stored_timezone: object = None
) -> str | None:
    explicit_timezone = str(stored_timezone or "").strip() or None
    if explicit_timezone is not None:
        return explicit_timezone
    if (
        str(task_type or "").strip() == "weekly_summary"
        and str(interval or "").strip().lower() == "weekly"
    ):
        return "UTC"
    return None


def parse_structured_schedule(interval: object, timezone_name: object = None) -> SchedulePreset:
    text = str(interval or "")
    timezone_value = _timezone_value(timezone_name)
    rolling = _CANONICAL_ROLLING_RE.fullmatch(text)
    if rolling:
        if timezone_value is not None:
            raise SchedulePresetError("Rolling minute/hour schedules do not accept a timezone")
        quantity, frequency = rolling.groups()
        return SchedulePreset(text, frequency, int(quantity), None, None)

    fixed = _CANONICAL_FIXED_RE.fullmatch(text)
    if fixed:
        if timezone_value is None:
            raise SchedulePresetError("Fixed-time schedules require a timezone")
        _validate_timezone(timezone_value)
        frequency, hour, minute = fixed.groups()
        return SchedulePreset(
            text,
            frequency,
            1,
            f"{hour}:{minute}",
            timezone_value,
        )

    raise SchedulePresetError(
        "Schedule interval must be exactly 'every N minutes', 'every N hours', "
        "'daily at HH:MM', or 'weekly at HH:MM'"
    )


def parse_runtime_schedule(interval: object, timezone_name: object = None) -> SchedulePreset:
    text = str(interval or "").strip().lower()
    timezone_value = None if timezone_name is None or timezone_name == "" else str(timezone_name)
    _validate_timezone(timezone_value)

    if text in {"daily", "weekly"}:
        return SchedulePreset(text, text, 1, "00:30", timezone_value, legacy=True)

    rolling_parts = text.split()
    if (
        len(rolling_parts) == 3
        and rolling_parts[0] == "every"
        and re.fullmatch(r"\d+", rolling_parts[1])
        and int(rolling_parts[1]) > 0
        and rolling_parts[2] in {"minute", "minutes", "hour", "hours"}
    ):
        if timezone_value is not None:
            raise SchedulePresetError("Rolling minute/hour schedules do not accept a timezone")
        _, quantity_text, raw_unit = rolling_parts
        quantity = int(quantity_text)
        frequency = "hours" if raw_unit.startswith("hour") else "minutes"
        canonical = f"every {quantity} {frequency}"
        return SchedulePreset(
            canonical,
            frequency,
            quantity,
            None,
            None,
            legacy=text != canonical,
        )

    fixed_text = text
    if text.startswith("daily at "):
        fixed_text = f"daily at {text.removeprefix('daily at ').strip()}"
    fixed = _LEGACY_FIXED_RE.fullmatch(fixed_text)
    if fixed:
        frequency, hour_text, minute_text = fixed.groups()
        hour = int(hour_text)
        minute = int(minute_text)
        if hour > 23 or minute > 59:
            raise SchedulePresetError(f"Unsupported schedule interval: {interval}")
        at_time = f"{hour:02d}:{minute:02d}"
        canonical = f"{frequency} at {at_time}"
        return SchedulePreset(
            canonical,
            frequency,
            1,
            at_time,
            timezone_value,
            legacy=text != canonical or timezone_value is None,
        )

    raise SchedulePresetError(f"Unsupported schedule interval: {interval}")
