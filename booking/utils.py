import random
import string
import logging
import os
from .database import conn
from fastapi import HTTPException, status
import aioredis
from concurrent_log_handler import ConcurrentRotatingFileHandler

# redis connection
# client = aioredis.from_url('redis://default@54.198.65.205:6379', decode_responses=True) in production

client =  aioredis.from_url('redis://localhost', decode_responses=True) # in local testing

def setup_logging():
    logger = logging.getLogger("auth_log") # create logger
    if not logger.hasHandlers(): # check if handlers already exist
        logger.setLevel(logging.INFO) # set log level

        # create log directory if it doesn't exist
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)

        # create a file handler
        file_handler = ConcurrentRotatingFileHandler(
            os.path.join(log_dir, "auth.log"), 
            maxBytes=10000, # 10KB 
            backupCount=500
        )
        file_handler.setLevel(logging.INFO) # The lock file .__auth.lock is created here by ConcurrentRotatingFileHandler

        #  create a console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # create a formatter
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                                      datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        #  add the handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger


rand_numbers = set()

def  random_number():
    digits = string.digits
    appointment_id = ''.join(random.choice(digits) for i in range(6))
    if appointment_id not in rand_numbers:
        rand_numbers.add(appointment_id)
        return appointment_id
    else:
        return random_number()

async def cache_appointment(data: dict):
    appointment_key = f"appointment:{data['appointment_date']}:{data['CIN']}:{data['appointment_time']}"
    await client.hset(appointment_key, mapping={
        "doctor_name": data['doctor_name'],
        "patient_name": data['patient_name'],
        "appointment_date": data['appointment_date'],
        "appointment_time": data['appointment_time'],
        "CIN": data['CIN'],
        "status": data['status'],
        "appointment_id": data['appointment_id']
    })
    await client.expire(appointment_key, 8 * 24 * 60 * 60)  # Cache for 7 days
    print("Appointment cached successfully")

async def get_cached_appointments(data: dict):
    keys = await client.keys(f"appointment:{data['appointment_date']}:{data['CIN']}*")
    # print(keys) #debugging
    appointments = []
    for key in keys:
        cached_data = await client.hgetall(key)
        if cached_data:
            appointments.append(cached_data)
    if appointments:
        # print(appointments) #debugging
        print("Appointments fetched from cache")
        return appointments
    return None

async def delete_cached_appointment(data: dict):
    keys = await client.keys(f"appointment:{data['appointment_date']}:{data['CIN']}:{data['appointment_time']}")
    for key in keys:
        await client.delete(key)
    print("Appointment deleted from cache")
    return 0

async def insert_in_db(form: dict):
            form["appointment_id"] = random_number() # generate random appointment id
            form["status"] = "false" # set status to false

            new_appointment = await conn.booking.appointment.insert_one(form)
            count_doc = await conn.booking.appointment.count_documents({
                "doctor_name": form["doctor_name"],
                "CIN": form["CIN"],
                "appointment_date": form["appointment_date"]
            })
            await conn.booking.appointment.update_one({
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
            return (form)