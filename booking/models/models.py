import json
from pydantic import BaseModel
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

class Booking(BaseModel):
    doctor_name: str = Field(..., title = "doctor name")
    patient_name: str = Field(..., title = "patient name")
    email: str = Field(..., title = "Email of patient")
    appointment_date: str = Field(..., title = "Appointment date")
    appointment_time: str = Field(..., title = "Appointment time")
    CIN: str = Field(..., title = "CIN of doctor")

class Reschedule_Appointment(BaseModel):
    CIN: str = Field(..., title = "CIN of doctor")
    appointment_date: str = Field(..., title = "Appointment date")
    appointment_time: str = Field(..., title = "Appointment time")
    reason: str = Field(..., title = "Reason for rescheduling")
    appointment_id: str = Field(..., title = "Appointment ID")

class cancel(BaseModel):
    appointment_id: str = Field(..., title = "Appointment ID")

class done(BaseModel):
    appointment_id: List[str] = Field(..., title = "Appointment ID")

class Doctor(BaseModel):
    full_name: str = Field(None, title="Full Name of the User")
    email: EmailStr = Field(..., title="Email Address")
    CIN: str = Field(..., title="Username")
    password: str = Field(..., title="Password")
    password2: str = Field(..., title="Confirm Password")
    phone_number: int = Field(..., min_length=10, title="Phone Number")
    disabled: bool = Field(default=False, title="User Account Status")

class res(BaseModel):
    doctor_name: Optional[str]
    appointment_date: Optional[str]
    appointment_time: Optional[str]
    appointment_id: Optional[str]
    CIN: Optional[str]
    status: bool

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()  # For Pydantic v2
        elif hasattr(obj, 'dict'):
            return obj.dict()  # For older Pydantic versions
        return super().default(obj)