from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import re
from .databse import conn
import aioredis

book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

client =  aioredis.from_url('redis://localhost', decode_responses=True)

async def cache(data: str):
    CacheData = str(await client.hgetall(f"data:{data}"))

    if CacheData.startswith("{"):
        return None
    if CacheData:
        print("data is cached", CacheData)
        return CacheData

    user = conn.booking.appointment.find_one({"email": data})
    if user:
        print("Searching for data in database")
        await client.hset(f"data:{data}", mapping={
            "doctor_name": str(user["doctor_name"]),
            "patient_name": str(user["patient_name"]),
            "email": str(user["email"]),
            "appointment_date": str(user["appointment_date"]),
            "appointment_time": str(user["appointment_time"])
        })
        return {
            "doctor_name": str(user["doctor_name"]),
            "patient_name": str(user["patient_name"]),
            "email": str(user["email"]),
            "appointment_date": str(user["appointment_date"]),
            "appointment_time": str(user["appointment_time"])
        }
    return None

@book.get("/", response_class=HTMLResponse)
async def read_appointment(request: Request):
    # Use list() to properly convert cursor to list
    docs = list(conn.booking.appointment.find({}))
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


        #  check in cache
        cached_data = await cache(form_dict["email"])
        if cached_data:
            # new_appointment = conn.booking.appointment.insert_one(form_dict)
            # count_doc = conn.booking.appointment.count_documents({
            # "doctor_name": form_dict["doctor_name"],
            # "appointment_date": form_dict["appointment_date"]})
            # update_doc = conn.booking.appointment.update_one({
            # "_id": new_appointment.inserted_id}, {
            # "$set": {"number_of_appointments": count_doc}}) 
            return cached_data
            

        # Check if doctor exists
        doctor_appointment = conn.booking.doctor.find_one({
            "full_name": form_dict["doctor_name"],
            "user_name": form_dict["user_name"]
        })
        if not doctor_appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found, please choose a different doctor.")
        
        # Convert appointment time to datetime for comparisons
        appointment_datetime = datetime.strptime(f"{form_dict['appointment_date']} {form_dict['appointment_time']}", "%Y-%m-%d %H:%M")
        
        # Check for existing appointments with 30-minute overlap
        existing_appointments = list(conn.booking.appointment.find({
            "doctor_name": form_dict["doctor_name"],
            "appointment_date": form_dict["appointment_date"]
        }))

        for existing_appt in existing_appointments:
            existing_appt_datetime = datetime.strptime(f"{existing_appt['appointment_date']} {existing_appt['appointment_time']}", "%Y-%m-%d %H:%M")
            
            # Check if new appointment is within 30 minutes before or after an existing appointment
            if abs(appointment_datetime - existing_appt_datetime) < timedelta(minutes=30):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is too close to an existing appointment. Please choose a different time.")

        # Insert the new appointment
        new_appointment = conn.booking.appointment.insert_one(form_dict)
        count_doc = conn.booking.appointment.count_documents({
            "doctor_name": form_dict["doctor_name"],
            "appointment_date": form_dict["appointment_date"]
        })
        update_doc = conn.booking.appointment.update_one({
            "_id": new_appointment.inserted_id
        }, {
            "$set": {
                "number_of_appointments": count_doc
        }}) 
        
        if not new_appointment.inserted_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to book appointment")

        # Redirect to GET endpoint to show updated list
        return RedirectResponse("http://127.0.0.1:8000/", status_code=status.HTTP_302_FOUND)
    
    except Exception as e:
        print(f"Error booking appointment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")
