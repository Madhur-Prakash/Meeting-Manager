import json
from pydantic import BaseModel
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

class Booking(BaseModel):
    user_name: str = Field(..., title = "User name")
    email: str = Field(..., title = "Email of user")
    meeting_date: str = Field(..., title = "Meeting date")
    meeting_time: str = Field(..., title = "Meeting time")
    CIN: str = Field(..., title = "CIN of user")

class Reschedule_Appointment(BaseModel):
    CIN: str = Field(..., title = "CIN of user")
    meeting_date: str = Field(..., title = "Meeting date")
    meeting_time: str = Field(..., title = "Meeting time")
    reason: str = Field(..., title = "Reason for rescheduling")
    meeting_id: str = Field(..., title = "Meeting ID")

class cancel(BaseModel):
    meeting_id: str = Field(..., title = "Meeting ID")

class done(BaseModel):
    meeting_id: List[str] = Field(..., title = "Meeting ID")

class Doctor(BaseModel):
    full_name: str = Field(None, title="Full Name of the User")
    email: EmailStr = Field(..., title="Email Address")
    CIN: str = Field(..., title="Username")
    password: str = Field(..., title="Password")
    password2: str = Field(..., title="Confirm Password")
    phone_number: int = Field(..., min_length=10, title="Phone Number")
    disabled: bool = Field(default=False, title="User Account Status")

class res(BaseModel):
    user_name: Optional[str]
    meeting_date: Optional[str]
    meeting_time: Optional[str]
    meeting_id: Optional[str]
    CIN: Optional[str]
    status: bool

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()  # For Pydantic v2
        elif hasattr(obj, 'dict'):
            return obj.dict()  # For older Pydantic versions
        return super().default(obj)