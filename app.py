from fastapi import FastAPI
from booking.patient_side import patient_book
from booking.doctor_side import doctor_book

app=FastAPI()
app.include_router(doctor_book)
app.include_router(patient_book)
