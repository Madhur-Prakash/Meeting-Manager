from pydantic import BaseModel

class Booking(BaseModel):
    doctor_name: str
    patient_name: str
    email: str
    appointment_date: str
    appointment_time: str
