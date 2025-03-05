from pydantic import BaseModel
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class Booking(BaseModel):
    doctor_name: str
    patient_name: str
    email: str
    appointment_date: str
    appointment_time: str
    status: bool =False

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