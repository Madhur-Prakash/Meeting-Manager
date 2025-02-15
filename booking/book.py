from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from . import models
from .databse import conn
import aioredis

book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

client =  aioredis.from_url('redis://localhost', decode_responses=True)

async def cache_appointment(data: dict):
    appointment_key = f"appointment:{data['appointment_date']}:{data['appointment_time']}:{data['email']} ; {data['patient_name']}"
    await client.hset(appointment_key, mapping={
        "doctor_name": data['doctor_name'],
        "patient_name": data['patient_name'],
        "appointment_date": data['appointment_date'],
        "appointment_time": data['appointment_time'],
        "user_name": data['user_name'],
    })
    await client.expire(appointment_key, 7 * 24 * 60 * 60)  # Cache for 7 days
    print("Appointment cached successfully")

async def get_cached_appointments(data: dict):
    keys = await client.keys(f"appointment:{data['appointment_date']}:{data['appointment_time']}*")
    print(keys) #debugging
    appointments = []
    for key in keys:
        cached_data = await client.hgetall(key)
        if cached_data:
            appointments.append(cached_data)
    if appointments:
        print(appointments) #debugging
        print("Appointments fetched from cache")
        return appointments
    return None

async def insert_in_db(form: dict):
            new_appointment = conn.booking.appointment.insert_one(form)
            count_doc = conn.booking.appointment.count_documents({
                "doctor_name": form["doctor_name"],
                "user_name": form["user_name"],
                "appointment_date": form["appointment_date"]
            })
            conn.booking.appointment.update_one({
                "_id": new_appointment.inserted_id
            }, {
                "$set": {
                    "number_of_appointments": count_doc
            }}) 

            
            if not new_appointment.inserted_id:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to book appointment")
            print("Appointment booked successfully") #debugging
            # data caching after all the validation are done and appointment is booked
            await cache_appointment(form)


@book.get("/", response_class=HTMLResponse)
async def read_appointment(request: Request):
    # Use list() to properly convert cursor to list
    docs = list(conn.booking.appointment.find({}))
    new_docs = []
    
    for doc in docs:
        new_docs.append({
            "id": str(doc["_id"]),  # Convert ObjectId to string
            "doctor_name": doc["doctor_name"],
            "user_name": doc["user_name"],
            "patient_name": doc["patient_name"],
            "email": doc["email"],
            "appointment_date": doc["appointment_date"],
            "appointment_time": doc["appointment_time"]
        })
    
    return templates.TemplateResponse("index.html", {"request": request, "new_docs": new_docs})

@book.post("/", status_code=status.HTTP_302_FOUND, response_model=models.res)
async def book_appointment(request: Request):
    try:
        form = await request.form()
        form_dict = dict(form)
        
        # Check if data is cached
        cached_data = await get_cached_appointments(form_dict)
        # Convert appointment time to datetime for comparisons
        appointment_datetime = datetime.strptime(f"{form_dict['appointment_date']} {form_dict['appointment_time']}", "%Y-%m-%d %H:%M")
        if cached_data:
            # compare the cached appointment time with the new appointment time
            for existing_appt in cached_data:
                existing_appt_datetime = datetime.strptime(f"{existing_appt['appointment_date']} {existing_appt['appointment_time']}", "%Y-%m-%d %H:%M")
                
                # Check if new appointment is within 30 minutes before or after an existing appointment
                if abs(appointment_datetime - existing_appt_datetime) < timedelta(minutes=30):
                    print("Data checked in cache for appointment") #debugging
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is too close to an existing appointment. Please choose a different time.")   
            # insert in db if no conflict
            await insert_in_db(form_dict)   
            # Return the first cached appointment
            return models.res(**cached_data[0])
        
        print("cache returned None") #debugging
        # covert every date-time into datetime object for comparison
        existing_appointments = list(conn.booking.appointment.find({
            "doctor_name": form_dict["doctor_name"],
            "appointment_date": form_dict["appointment_date"],
            "user_name": form_dict["user_name"]
        }))

        for existing_appt in existing_appointments:
            existing_appt_datetime = datetime.strptime(f"{existing_appt['appointment_date']} {existing_appt['appointment_time']}", "%Y-%m-%d %H:%M")
            
            # Check if new appointment is within 30 minutes before or after an existing appointment
            if abs(appointment_datetime - existing_appt_datetime) < timedelta(minutes=30):
                print("db hit for appointment") #debugging
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is too close to an existing appointment. Please choose a different time.")

        # Insert the new appointment into the database
        await insert_in_db(form_dict)
        
        # Return the new appointment details
        return models.res(**form_dict)

    except Exception as e:
        print(f"Error booking appointment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")
