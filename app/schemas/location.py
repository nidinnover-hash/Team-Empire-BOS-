from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

LocationSource = Literal["gps", "ip_geolocation", "manual_checkin", "google_maps"]
CheckinType = Literal["arrival", "departure", "meeting", "site_visit", "other"]


class LocationTrackingCreate(BaseModel):
    employee_id: int
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_m: float | None = Field(None, ge=0)
    altitude_m: float | None = None
    source: LocationSource = "gps"
    address: str | None = Field(None, max_length=500)
    ip_address: str | None = Field(None, max_length=45)


class LocationTrackingRead(BaseModel):
    id: int
    organization_id: int
    employee_id: int
    latitude: float
    longitude: float
    accuracy_m: float | None
    altitude_m: float | None
    source: str
    address: str | None
    ip_address: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LocationCheckinCreate(BaseModel):
    employee_id: int
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    place_name: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=2000)
    checkin_type: CheckinType = "arrival"


class LocationCheckinRead(BaseModel):
    id: int
    organization_id: int
    employee_id: int
    latitude: float
    longitude: float
    place_name: str | None
    notes: str | None
    checkin_type: str
    checked_out_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LocationConsentUpdate(BaseModel):
    employee_id: int
    consent: bool


class EmployeeLocationRead(BaseModel):
    employee_id: int
    employee_name: str
    role: str | None
    job_title: str | None = None
    latitude: float
    longitude: float
    accuracy_m: float | None
    source: str
    address: str | None
    last_seen: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _fill_job_title_alias(self) -> "EmployeeLocationRead":
        if self.job_title in (None, ""):
            self.job_title = self.role
        return self
