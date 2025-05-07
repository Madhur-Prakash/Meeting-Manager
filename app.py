from fastapi import FastAPI
from booking.src.patient_side import patient_book
from booking.src.doctor_side import doctor_book
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI()
app.include_router(doctor_book)
app.include_router(patient_book)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
