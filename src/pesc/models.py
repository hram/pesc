from dataclasses import dataclass, field


@dataclass
class AccountInfo:
    account_id: str
    balance_text: str


@dataclass
class IndicationScale:
    meter_scale_id: int
    scale_name: str | None = None
    previous_reading: float | None = None
    previous_reading_date: str | None = None
    unit: str | None = None


@dataclass
class Meter:
    registration: str
    name: str | None
    subservice_id: int | None
    number_of_digits_right: int | None
    indications: list[IndicationScale] = field(default_factory=list)


@dataclass
class MeterReading:
    # key format: "{registration}:{scale_id}"
    meter: str
    kind: str
    value: float
