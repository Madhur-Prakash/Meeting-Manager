from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class Booking(BaseModel):
    doctor_name: str
    patient_name: str
    email: str
    appointment_date: str
    appointment_time: str

class User(BaseModel):
    full_name: str = Field(None, title="Full Name of the User")
    email: EmailStr = Field(..., title="Email Address")
    user_name: str = Field(..., title="Username")
    password: str = Field(..., title="Password")
    password2: str = Field(..., title="Confirm Password")
    phone_number: int = Field(..., min_length=10, title="Phone Number")
    disabled: bool = Field(default=False, title="User Account Status")
