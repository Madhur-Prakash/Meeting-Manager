from fastapi import APIRouter,Request,HTTPException,status
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from .databse import conn

book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

@book.get("/", response_class=HTMLResponse)
async def read_appointment(request: Request):
    docs = conn.prescription.book_appoinment.find({})
    new_docs = []
    for doc in docs:
        new_docs.append({
            "id": doc["_id"],
            "doctor_name": doc["doctor_name"],
            "patient_name": doc["patient_name"],
            "email": doc["email"],
            "appointment_date": doc["appointment_date"],
            "appointment_time": doc["appointment_time"]
        })
    
    return templates.TemplateResponse("index.html", {"request": request, "new_docs": new_docs})

book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

@book.get("/", response_class=HTMLResponse)
async def read_appointment(request: Request):
    # Use list() to properly convert cursor to list
    docs = list(conn.prescription.book_appoinment.find({}))
    new_docs = []
    
    for doc in docs:
        new_docs.append({
            "id": str(doc["_id"]),  # Convert ObjectId to string
            "doctor_name": doc["doctor_name"],
            "patient_name": doc["patient_name"],
            "email": doc["email"],
            "appointment_date": doc["appointment_date"],
            "appointment_time": doc["appointment_time"]
        })
    
    return templates.TemplateResponse("index.html",{"request": request, "new_docs": new_docs})

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from .databse import conn

book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

@book.get("/", response_class=HTMLResponse)
async def read_appointment(request: Request):
    # Use list() to properly convert cursor to list
    docs = list(conn.prescription.book_appoinment.find({}))
    new_docs = []
    
    for doc in docs:
        new_docs.append({
            "id": str(doc["_id"]),  # Convert ObjectId to string
            "doctor_name": doc["doctor_name"],
            "patient_name": doc["patient_name"],
            "email": doc["email"],
            "appointment_date": doc["appointment_date"],
            "appointment_time": doc["appointment_time"]
        })
    
    return templates.TemplateResponse("index.html", {"request": request, "new_docs": new_docs})

@book.post("/", response_class=HTMLResponse)
async def book_appointment(request: Request):
    try:
        form = await request.form()
        form_dict = dict(form)

        # Check if doctor exists
        doctor_appointment = conn.prescription.book_appoinment.find_one({
            "doctor_name": form_dict["doctor_name"]
        })

        # Convert appointment time to datetime for comparisons
        appointment_datetime = datetime.strptime(f"{form_dict['appointment_date']} {form_dict['appointment_time']}", "%Y-%m-%d %H:%M")
        
        # Check for existing appointments with 30-minute overlap
        existing_appointments = list(conn.prescription.book_appoinment.find({
            "doctor_name": form_dict["doctor_name"],
            "appointment_date": form_dict["appointment_date"]
        }))

        for existing_appt in existing_appointments:
            existing_appt_datetime = datetime.strptime(f"{existing_appt['appointment_date']} {existing_appt['appointment_time']}", "%Y-%m-%d %H:%M")
            
            # Check if new appointment is within 30 minutes before or after an existing appointment
            if abs(appointment_datetime - existing_appt_datetime) < timedelta(minutes=30):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is too close to an existing appointment. Please choose a different time.")

        # Insert the new appointment
        result = conn.prescription.book_appoinment.insert_one(form_dict)
        
        if not result.inserted_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to book appointment")

        # Redirect to GET endpoint to show updated list
        return RedirectResponse("http://127.0.0.1:8000/", status_code=status.HTTP_302_FOUND)
    
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid date or time format. Please use YYYY-MM-DD and HH:MM format."
        )
    except Exception as e:
        print(f"Error booking appointment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")
