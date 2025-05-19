import os
import sys
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from ..config.redis_config import client
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")
from models import models
from datetime import datetime, timedelta
from ..helper.utils import setup_logging, cache_appointment, delete_cached_appointment, insert_in_db, send_email, send_email_ses, create_new_log
import traceback
from ..config.database import conn

doctor_book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

logger = setup_logging() # initialize logger

@doctor_book.get("/healthz_appoint")
def health_check():
    return {"status": "ok"}

@doctor_book.get("/doctor/appointment/{CIN}", status_code=status.HTTP_200_OK)
async def get_all(CIN: str):
    try:
        appointments =  await conn.booking.appointment.find({"CIN": CIN}).sort([("appointment_date", 1), ("appointment_time", 1)]).to_list(length=None)
        print(appointments) #debugging
        cache_keys = await client.keys(f"appointment:{CIN}:*")
        if cache_keys:
            print("Cache data found")
            cached_appointments = []
            for key in cache_keys:
                appointment_data = await client.hgetall(key)
                if appointment_data:
                    cached_appointments.append(appointment_data)
            return cached_appointments
        
        print("No cache data found") #debugging
        appo = []
        for appointment in appointments:
            appointment_data = {
                "patient_name": appointment["patient_name"],
                "appointment_date": appointment["appointment_date"],
                "appointment_time": appointment["appointment_time"]
            }
            appo.append(appointment_data)
            
            # Cache the appointment
            await client.hset(
                f"appointment:{CIN}:{appointment['_id']}", mapping=appointment_data)
        
        return appo
    
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error fetching appointments: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error fetching appointments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
@doctor_book.get("/doctor/{CIN}/delete_cached_appointments", status_code=status.HTTP_200_OK)
async def delete_cached_appointments(CIN: str):
    try:
        cache_keys = await client.keys(f"appointment:{CIN}:*")
        if cache_keys:
            await client.delete(*cache_keys)
            create_new_log("info", f"Deleted cached appointments for CIN {CIN}", "/api/backend/Appointment")
            logger.info(f"Deleted cached appointments for CIN {CIN}")
            return {"message": f"Deleted {len(cache_keys)} cached appointments for CIN {CIN}", "status_code": status.HTTP_200_OK}
        else:
            return {"message": f"No cached appointments found for CIN {CIN}", "status_code": status.HTTP_404_NOT_FOUND}
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error deleting cached appointments: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error deleting cached appointments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@doctor_book.post("/doctor/appointment/reschedule", status_code=status.HTTP_302_FOUND)
async def reschedule(data: models.Reschedule_Appointment):
    try:
        form = dict(data)
        form_data = dict(form)

        # required fields
        required_fields = ["appointment_date", "appointment_time", "reason", "appointment_id", "CIN"]
        for field in required_fields:
            if field not in form_data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All fields are required")
        
        doctor = await conn.public_profile_data.doctor.find_one({"CIN": form_data["CIN"]})
        if not doctor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")


        new_appointment_date = form_data["appointment_date"]
        new_appointment_time = form_data["appointment_time"]
        reason = form_data["reason"]

        new_appointment_datetime = datetime.strptime(f"{new_appointment_date} {new_appointment_time}", "%d-%m-%y %H:%M")
        
        # Check if the new appointment date is in the past
        # if new_appointment_datetime < datetime.now().isoformat():
        #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Appointment date cannot be in the past")

        existing_appointment = await conn.booking.appointment.find_one({"appointment_id": form_data['appointment_id']})
        if not existing_appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        # Check if the slot is already booked
        if(existing_appointment['appointment_date'] == new_appointment_date and existing_appointment['appointment_time'] == new_appointment_time):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is already booked. Please choose a different time.")

        existing_appointment_time = await conn.booking.appointment.find({
            "appointment_date": new_appointment_date}).to_list(length=None)
        print("existing_appointment_time", existing_appointment_time)
        for existing_appo_time in existing_appointment_time:
            existing_time = datetime.strptime(f"{existing_appo_time['appointment_date']} {existing_appo_time['appointment_time']}", "%d-%m-%y %H:%M")

            # Check if new appointment is within 30 minutes before or after an existing appointment
            if abs(existing_time - new_appointment_datetime) < timedelta(minutes=int(doctor['avg_appointment_duration'])):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is too close to an existing appointment. Please choose a different time.")
            
#  ************************************fixing the number_of_appointments fiels in the database****************************************

        if(existing_appointment['appointment_date'] == new_appointment_date):
            await conn.booking.appointment.count_documents({
                "doctor_name": existing_appointment["doctor_name"],
                "CIN": existing_appointment["CIN"],
                "appointment_date": new_appointment_date
            })
            # Update the current appointment's date and time
            await conn.booking.appointment.update_one(
                {"appointment_id": form_data['appointment_id']},
                {"$set": {
                    "appointment_date": new_appointment_date,
                    "appointment_time": new_appointment_time}})
            
            updated_mongo_doc = {
                "doctor_name": existing_appointment["doctor_name"],
                "CIN": existing_appointment["CIN"],
                "patient_name": existing_appointment["patient_name"],
                "email": existing_appointment["email"],
                "appointment_date": new_appointment_date,
                "appointment_time": new_appointment_time,
                "status": existing_appointment["status"],
                "appointment_id": form_data['appointment_id']}
            
            await cache_appointment(updated_mongo_doc) # updating the cache with the new appointment details
            await delete_cached_appointment(existing_appointment) # deleting the old appointment from the cache

            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4;">
    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: #f4f4f4; padding: 20px;">
        <tr>
            <td align="center">
                <table width="600px" cellspacing="0" cellpadding="0" style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0px 0px 10px rgba(0,0,0,0.1);">
                    <tr>
                        <td align="center">
                            <h2 style="color: #2C3E50;">Appointment Reschedule Confirmation</h2>
                            <p style="color: #555; font-size: 16px;">Dear <strong>{existing_appointment['patient_name']}</strong>,</p>
                            <p style="color: #555; font-size: 16px;">Your appointment with <strong>CuraDocs</strong> has been successfully rescheduled. Below are your updated appointment details:</p>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <table width="100%" cellspacing="0" cellpadding="10" style="border-collapse: collapse;">
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">Doctor:</td>
                                    <td style="color: #555; font-size: 16px;">Dr. {existing_appointment['doctor_name']}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">New Date:</td>
                                    <td style="color: #555; font-size: 16px;">{new_appointment_date}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">New Time:</td>
                                    <td style="color: #555; font-size: 16px;">{new_appointment_time}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">Reason for Rescheduling:</td>
                                    <td style="color: #555; font-size: 16px;">{reason}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <p style="color: #555; font-size: 16px;">Please arrive at least <strong>15 minutes</strong> before your scheduled appointment.</p>
                            <p style="color: #555; font-size: 16px;">If you need any further assistance, feel free to contact us.</p>
                            <p style="color: #555; font-size: 16px;">We appreciate your trust in CuraDocs and look forward to serving you.</p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding-top: 20px;">
                            <p style="color: #777; font-size: 14px;">Best regards,</p>
                            <p style="color: #2C3E50; font-size: 16px; font-weight: bold;">CuraDocs Team</p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding-top: 30px; border-top: 1px solid #ddd;">
                            <p style="color: #888; font-size: 12px;">© 2025 CuraDocs. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

            sent_mail = send_email(existing_appointment["email"], "Appointment Reschedule Confirmation", html_body, retries=3, delay=5)
            if not sent_mail:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send email. Please try again later.")

            create_new_log("info", f"Appointment rescheduled successfully: {form_data['appointment_id']}", "/api/backend/Appointment")
            logger.info(f"Appointment rescheduled successfully: {form_data['appointment_id']}")
            return {"message": "Appointment rescheduled successfully", "appointment_id": form_data['appointment_id'], "status": status.HTTP_200_OK}

        # If the date has changed, update the number of appointments for the old date
        elif new_appointment_date != existing_appointment['appointment_date']:
            #  delete the old appointment from the database
            await conn.booking.appointment.delete_one({"appointment_id": form_data['appointment_id']})

            #  delete the old appointment from the cache
            await delete_cached_appointment(existing_appointment)

            #  insert the new appointment into the database
            updated_mongo_doc = {
                "doctor_name": existing_appointment["doctor_name"],
                "CIN": existing_appointment["CIN"],
                "patient_name": existing_appointment["patient_name"],
                "email": existing_appointment["email"],
                "appointment_date": new_appointment_date,
                "appointment_time": new_appointment_time}
            
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4;">
    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: #f4f4f4; padding: 20px;">
        <tr>
            <td align="center">
                <table width="600px" cellspacing="0" cellpadding="0" style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0px 0px 10px rgba(0,0,0,0.1);">
                    <tr>
                        <td align="center">
                            <h2 style="color: #2C3E50;">Appointment Reschedule Confirmation</h2>
                            <p style="color: #555; font-size: 16px;">Dear <strong>{existing_appointment['patient_name']}</strong>,</p>
                            <p style="color: #555; font-size: 16px;">Your appointment with <strong>CuraDocs</strong> has been successfully rescheduled. Below are your updated appointment details:</p>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <table width="100%" cellspacing="0" cellpadding="10" style="border-collapse: collapse;">
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">Doctor:</td>
                                    <td style="color: #555; font-size: 16px;">Dr. {existing_appointment['doctor_name']}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">New Date:</td>
                                    <td style="color: #555; font-size: 16px;">{new_appointment_date}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">New Time:</td>
                                    <td style="color: #555; font-size: 16px;">{new_appointment_time}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">Reason for Rescheduling:</td>
                                    <td style="color: #555; font-size: 16px;">{reason}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <p style="color: #555; font-size: 16px;">Please arrive at least <strong>15 minutes</strong> before your scheduled appointment.</p>
                            <p style="color: #555; font-size: 16px;">If you need any further assistance, feel free to contact us.</p>
                            <p style="color: #555; font-size: 16px;">We appreciate your trust in CuraDocs and look forward to serving you.</p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding-top: 20px;">
                            <p style="color: #777; font-size: 14px;">Best regards,</p>
                            <p style="color: #2C3E50; font-size: 16px; font-weight: bold;">CuraDocs Team</p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding-top: 30px; border-top: 1px solid #ddd;">
                            <p style="color: #888; font-size: 12px;">© 2025 CuraDocs. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

            sent_mail = send_email(existing_appointment["email"], "Appointment Reschedule Confirmation", html_body, retries=3, delay=5)
            if not sent_mail:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send email. Please try again later.")

            new_appointment = await insert_in_db(updated_mongo_doc)
            create_new_log("info", f"Appointment rescheduled successfully: {new_appointment['appointment_id']}", "/api/backend/Appointment")
            logger.info(f"Appointment rescheduled successfully: {new_appointment['appointment_id']}")
            return {"message": "Appointment rescheduled successfully", "appointment_id": new_appointment['appointment_id'], "status": status.HTTP_200_OK}
    
#****************************************************************************************************************************************************
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error rescheduling appointment: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error rescheduling appointment: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")
    
@doctor_book.post("/doctor/appointment/done", status_code=status.HTTP_302_FOUND)
async def done_appointment(data: models.done):
    try:
        form_data = dict(data)
        appointment_id = form_data['appointment_id']
        if not appointment_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Appointment ID is required")
        
        # await conn.booking.appointment.update_one({"appointment_id": appointment_id}, {"$set": {"status": appointment_status}})
        for appointment in appointment_id:
            existing_appointment = await conn.booking.appointment.find_one({"appointment_id": appointment})
            if not existing_appointment:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
            await conn.booking.temp_appointment.insert_one(existing_appointment)
            await conn.booking.appointment.delete_one({"appointment_id": appointment})
            await delete_cached_appointment(existing_appointment)
            create_new_log("info", f"Appointment status updated successfully: {appointment_id}", "/api/backend/Appointment")
            logger.info(f"Appointment status updated successfully: {appointment_id}")
        return {"message": "Appointment status updated successfully", "appointment_id": appointment_id}
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error updating appointment status: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error updating appointment status: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")
    


@doctor_book.get("/doctor/previous_appointment/{CIN}", status_code=status.HTTP_200_OK)
async def doctor_get_previous_appointment(CIN: str):
    try:
        appointments =  await conn.booking.temp_appointment.find({"CIN": CIN}).sort([("appointment_date", 1), ("appointment_time", 1)]).to_list(length=None)
        print(appointments) #debugging
        cache_keys = await client.keys(f"appointment:{CIN}:*")
        if cache_keys:
            print("Cache data found")
            cached_appointments = []
            for key in cache_keys:
                appointment_data = await client.hgetall(key)
                if appointment_data:
                    cached_appointments.append(appointment_data)
            return cached_appointments
        
        print("No cache data found") #debugging
        appo = []
        for appointment in appointments:
            appointment_data = {
                "patient_name": appointment["patient_name"],
                "appointment_date": appointment["appointment_date"],
                "appointment_time": appointment["appointment_time"]
            }
            appo.append(appointment_data)
            
            # Cache the appointment
            await client.hset(f"previous_appointment:{CIN}:{appointment['_id']}", mapping=appointment_data)
            await client.expire(f"previous_appointment:{CIN}:{appointment['_id']}", 60 * 60 * 24 * 7)
        return appo
    
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error fetching appointments: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error fetching appointments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
@doctor_book.get("/doctor/refresh_previous_appointment/{CIN}", status_code=status.HTTP_200_OK)
async def doctor_refresh_previous_appointment(CIN: str):
    try:
        cache_keys = await client.keys(f"previous_appointment:{CIN}:*")
        if cache_keys:
            await client.delete(*cache_keys)
            create_new_log("info", f"Deleted cached previous appointments for CIN {CIN}", "/api/backend/Appointment")
            logger.info(f"Deleted cached previous appointments for CIN {CIN}")
            return {"message": f"Deleted {len(cache_keys)} cached previous appointments for CIN {CIN}", "status_code": status.HTTP_200_OK}
        else:
            return {"message": f"No cached previous appointments found for CIN {CIN}", "status_code": status.HTTP_404_NOT_FOUND}
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error deleting cached previous appointments: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error deleting cached previous appointments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))