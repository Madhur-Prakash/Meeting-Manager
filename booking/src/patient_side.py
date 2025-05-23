from fastapi import APIRouter, HTTPException, status
from collections import defaultdict
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")
from models import models
import traceback
from booking.config.redis_config import client
from ..helper.utils import get_busy_date, setup_logging, cache_appointment, get_cached_appointments, insert_in_db, delete_cached_appointment, send_email, send_email_ses, create_new_log, set_appointment_slot, get_appointment_slot, set_busy_date
from ..config.database import conn

patient_book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

logger = setup_logging() # initialize logger


@patient_book.get("/patient/appointment/{email}", status_code=status.HTTP_200_OK)
async def get_all(email: str):
    try:
        cache_keys = await client.keys(f"appointment:{email}:*")
        if cache_keys:
            print("Cache data found")
            cached_appointments = []
            for key in cache_keys:
                appointment_data = await client.hgetall(key)
                if appointment_data:
                    cached_appointments.append(appointment_data)
            return cached_appointments
        
        print("No cache data found") #debugging
        appointments =  await conn.booking.appointment.find({"email": email}).sort([("appointment_date", 1), ("appointment_time", 1)]).to_list(length=None)
        print(appointments) #debugging
        appo = []
        for appointment in appointments:
            appointment_data = {
                "doctor_name": appointment["doctor_name"],
                "appointment_date": appointment["appointment_date"],
                "appointment_time": appointment["appointment_time"],
                "CIN": appointment["CIN"],
                "status": appointment["status"],
                "appointment_id": appointment["appointment_id"],
                "number_of_appointments": appointment["number_of_appointments"]
            }
            appo.append(appointment_data)
            
            # Cache the appointment
            await client.hset(f"appointment:{email}:{appointment['_id']}", mapping=appointment_data)
            await client.expire(f"appointment:{email}:{appointment['_id']}", 3600)  # Set expiration time to 1 hour
        
        return appo
    
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error fetching appointments: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error fetching appointments: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")


@patient_book.get("/patient/{email}/delete_cached_appointments", status_code=status.HTTP_200_OK)
async def delete_cached_appointments(email: str):
    try:
        cache_keys = await client.keys(f"appointment:{email}:*")
        if cache_keys:
            await client.delete(*cache_keys)
            create_new_log("info", f"Deleted cached appointments for email {email}", "/api/backend/Appointment")
            logger.info(f"Deleted cached appointments for email {email}")
            return {"message": f"Deleted {len(cache_keys)} cached appointments for email {email}", "status_code": status.HTTP_200_OK}
        else:
            return {"message": f"No cached appointments found for email {email}", "status_code": status.HTTP_404_NOT_FOUND}
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error deleting cached appointments: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error deleting cached appointments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@patient_book.post("/patient/appointment/book", status_code=status.HTTP_302_FOUND)
async def book_appointment(data: models.Booking):
    try:
        form = dict(data)
        form_dict = dict(form)
        

        required_fields = ["doctor_name", "CIN", "patient_name", "email", "appointment_date", "appointment_time"]
        for field in required_fields:
            if field not in form_dict:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All fields are required")
        
        doctor = await conn.public_profile_data.doctor.find_one({"CIN": form_dict["CIN"]})
        if not doctor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found, please choose a different doctor.")

        # Check if data is cached
        cached_data = await get_cached_appointments(form_dict)
        # Convert appointment time to datetime for comparisons
        appointment_datetime = datetime.strptime(f"{form_dict['appointment_date']} {form_dict['appointment_time']}", "%d-%m-%Y %H:%M")
        
        if cached_data:
            # Check if doctor exists
            doctor_appointment = await conn.auth.doctor.find_one({
            "full_name": form_dict["doctor_name"],
            "CIN": form_dict["CIN"]})
            if not doctor_appointment:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found, please choose a different doctor.")
        
            # check if user exist
            user = await conn.auth.patient.find_one({"email": form_dict["email"]})
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
            # compare the cached appointment time with the new appointment time
            for existing_appt in cached_data:
                existing_appt_datetime = datetime.strptime(f"{existing_appt['appointment_date']} {existing_appt['appointment_time']}",  "%d-%m-%Y %H:%M")
                
                # Check if new appointment is within 30 minutes before or after an existing appointment
                if abs(appointment_datetime - existing_appt_datetime) < timedelta(minutes=int(doctor['avg_appointment_duration'])):
                    print("Data checked in cache for appointment")
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is too close to an existing appointment. Please choose a different time.")   
            
            # insert in db if no conflict
            updated_form_dict = await insert_in_db(form_dict)   
            create_new_log("info", f"Appointment booked successfull: {form_dict}", "/api/backend/Appointment")
            logger.info(f"Appointment booked successfull: {form_dict}")
            # Return the first cached appointment
            return {"message": "Appointment booked successfully", "appointment_id": updated_form_dict['appointment_id'], "status": status.HTTP_201_CREATED}
        
        print("cache returned None")

        # Check if doctor exists
        doctor_appointment = await conn.auth.doctor.find_one({
            "full_name": form_dict["doctor_name"],
            "CIN": form_dict["CIN"]
        })
        if not doctor_appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found, please choose a different doctor.")
        
        # check if patient exist
        user = await conn.auth.patient.find_one({"email": form_dict["email"]})
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        # Convert cursor to list using .to_list()
        existing_appointments = await conn.booking.appointment.find({
            "doctor_name": form_dict["doctor_name"],
            "appointment_date": form_dict["appointment_date"],
            "CIN": form_dict["CIN"]
        }).to_list(length=None)

        # print("existing app:", existing_appointments)

        for existing_appt in existing_appointments:
            existing_appt_datetime = datetime.strptime(f"{existing_appt['appointment_date']} {existing_appt['appointment_time']}",  "%d-%m-%Y %H:%M")
            
            # Check if new appointment is within 30 minutes before or after an existing appointment
            if abs(appointment_datetime - existing_appt_datetime) < timedelta(minutes=int(doctor['avg_appointment_duration'])):
                print("db hit for appointment")
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is too close to an existing appointment. Please choose a different time.")

        html_body = f"""
                        <html>
<body style="font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4;">
    <table width="100%" cellspacing="0" cellpadding="0" style="background-color: #f4f4f4; padding: 20px;">
        <tr>
            <td align="center">
                <table width="600px" cellspacing="0" cellpadding="0" style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0px 0px 10px rgba(0,0,0,0.1);">
                    <tr>
                        <td align="center">
                            <h2 style="color: #2C3E50;">Appointment Confirmation</h2>
                            <p style="color: #555; font-size: 16px;">Dear <strong>{form_dict['patient_name']}</strong>,</p>
                            <p style="color: #555; font-size: 16px;">Thank you for booking your appointment with <strong>CuraDocs</strong>. Below are your appointment details:</p>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <table width="100%" cellspacing="0" cellpadding="10" style="border-collapse: collapse;">
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">Doctor:</td>
                                    <td style="color: #555; font-size: 16px;">Dr. {form_dict['doctor_name']}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">Date:</td>
                                    <td style="color: #555; font-size: 16px;">{form_dict['appointment_date']}</td>
                                </tr>
                                <tr>
                                    <td style="background-color: #f8f8f8; color: #333; font-size: 16px; font-weight: bold;">Time:</td>
                                    <td style="color: #555; font-size: 16px;">{form_dict['appointment_time']}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <p style="color: #555; font-size: 16px;">Please arrive at least <strong> 15 minutes</strong> before your scheduled appointment. 
                            <p style="color: #555; font-size: 16px;">We look forward to assisting you with your healthcare needs.</p>
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
        # send a confirmation email to the patient
        email_sent = send_email(form_dict["email"], "Appointment Confirmation", html_body, retries=3, delay=5)
        if not email_sent:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send email. Please try again later.")   
        

        # Insert the new appointment into the database
        updated_form_dict = await insert_in_db(form_dict)
        create_new_log("info", f"Appointment booked successfull: {updated_form_dict['appointment_id']}", "/api/backend/Appointment")
        logger.info(f"Appointment booked successfull: {updated_form_dict['appointment_id']}")
        
        # Return the new appointment details
        return {"message": "Appointment booked successfully", "appointment_id": updated_form_dict['appointment_id'], "status": status.HTTP_201_CREATED}

    except Exception as e:
        print(f"Error booking appointment: {str(e)}")
        print(traceback.format_exc())
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error booking appointment: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error booking appointment: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")

@patient_book.post("/patient/appointment/reschedule", status_code=status.HTTP_302_FOUND)
async def reschedule(data: models.Reschedule_Appointment):
    try:
        form = dict(data)
        form_data = dict(form)
        
        #  required fields
        required_fields = ["appointment_date", "appointment_time", "reason", "appointment_id", "CIN"]
        for field in required_fields:
            if field not in form_data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All fields are required")

        doctor = await conn.booking.appointment.find_one({"CIN": form_data["CIN"]})
        if not doctor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found, please choose a different doctor.")

        new_appointment_date = form_data["appointment_date"]
        new_appointment_time = form_data["appointment_time"]
        reason = form_data["reason"]

        new_appointment_datetime = datetime.strptime(f"{new_appointment_date} {new_appointment_time}",  "%d-%m-%Y %H:%M")
        
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
            existing_time = datetime.strptime(f"{existing_appo_time['appointment_date']} {existing_appo_time['appointment_time']}", "%d-%m-%Y %H:%M")

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
        logger.error(f"Error rescheduling appointment: {formatted_error}")
        print(formatted_error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")


@patient_book.post("/patient/appointment/cancel", status_code=status.HTTP_302_FOUND)
async def cancel_appointment(data: models.cancel):
    try:
        form = dict(data)
        appointment = await conn.booking.appointment.find_one({"appointment_id": form["appointment_id"]})
        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")  
        await conn.booking.appointment.delete_one({"appointment_id": form["appointment_id"]})
        await delete_cached_appointment(appointment)
        create_new_log("info", f"Appointment cancelled successfully: {form['appointment_id']}", "/api/backend/Appointment")
        logger.info(f"Appointment cancelled successfully: {form['appointment_id']}")
        return {"message": "Appointment cancelled successfully", "appointment_id": form["appointment_id"], "status": status.HTTP_302_FOUND}
    
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error cancelling appointment: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error cancelling appointment: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")


@patient_book.get("/patient/get/available_slots/{CIN}/{date}", status_code=status.HTTP_200_OK)
async def get_available_slots(CIN: str, date: str):
    try:
        # Validate the date format
        try:
            selected_date = datetime.strptime(date, "%d-%m-%Y")
            date_str = selected_date.strftime("%d-%m-%Y")
            day_name = selected_date.strftime("%A").lower()  # Get day name in lowercase
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Please use DD-MM-YYYY")
        
        # Check cache first
        cache_data = await get_appointment_slot(date_str, CIN)
        if cache_data:
            logger.info(f"Cache hit for available slots: {CIN} on {date_str}")
            create_new_log("info", f"Cache hit for available slots: {CIN} on {date_str}", "/api/backend/Appointment")
            return cache_data

        # Get doctor details
        logger.info(f"Cache miss for available slots: {CIN} on {date_str}")
        doctor = await conn.public_profile_data.doctor.find_one({"CIN": CIN})
        if not doctor:
            logger.error(f"Doctor not found with CIN: {CIN}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

        # Get doctor's working time configuration
        try:
            avg_appointment_duration = int(doctor['avg_appointment_duration'])  # in minutes
            
            if 'working_time' not in doctor or not doctor['working_time']:
                raise KeyError("Working time not configured for doctor")
            
            # Handle index for scheduled day
            schedule_index = 0  # Default to first schedule
            
            # Get the working time configuration
            working_time = doctor['working_time'][schedule_index]
            
            # Extract working days and holidays
            working_days = [day.lower() for day in working_time.get('working_days', [])]
            holidays = [day.lower() for day in working_time.get('holidays', [])]
            
            # Check if the selected date is on a holiday
            if day_name in holidays:
                return {
                    "CIN": CIN,
                    "date": date_str,
                    "message": f"Doctor is not available on {day_name.capitalize()}s as it's marked as a holiday",
                    "available_slots": []
                }
            
            # Check if the selected date is a working day
            if working_days and day_name not in working_days:
                return {
                    "CIN": CIN,
                    "date": date_str,
                    "message": f"Doctor is not available on {day_name.capitalize()}s. Working days are: {', '.join(d.capitalize() for d in working_days)}",
                    "available_slots": []
                }
            
            # Extract time information as arrays - we'll consider all time slots
            start_times = working_time['start_time'] if isinstance(working_time['start_time'], list) else [working_time['start_time']]
            end_times = working_time['end_time'] if isinstance(working_time['end_time'], list) else [working_time['end_time']]
            start_break_times = working_time['start_break_time'] if isinstance(working_time['start_break_time'], list) else [working_time['start_break_time']]
            end_break_times = working_time['end_break_time'] if isinstance(working_time['end_break_time'], list) else [working_time['end_break_time']]
            
            # Ensure all arrays have the same length by extending shorter ones with their last value
            max_len = max(len(start_times), len(end_times), len(start_break_times), len(end_break_times))
            
            def extend_array(arr, target_len):
                if len(arr) < target_len and len(arr) > 0:
                    arr.extend([arr[-1]] * (target_len - len(arr)))
                return arr
                
            start_times = extend_array(start_times, max_len)
            end_times = extend_array(end_times, max_len)
            start_break_times = extend_array(start_break_times, max_len)
            end_break_times = extend_array(end_break_times, max_len)
            
        except (KeyError, IndexError, ValueError) as e:
            logger.error(f"Invalid doctor schedule configuration: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Invalid doctor schedule configuration: {str(e)}"
            )
        
        # Get all existing appointments for the doctor on the given date
        appointments = await conn.booking.appointment.find({
            "CIN": CIN,
            "appointment_date": date_str
        }).to_list(length=None)
        
        # Extract unavailable time slots
        unavailable_slots = []
        for appointment in appointments:
            appointment_time = appointment['appointment_time']
            appointment_datetime = datetime.strptime(f"{date_str} {appointment_time}", "%d-%m-%Y %H:%M")
            unavailable_slots.append(appointment_datetime)
        
        # Generate all possible time slots based on all working periods
        all_slots = []
        
        # Process each time slot for the day
        for i in range(len(start_times)):
            try:
                # Convert string times to datetime objects for easier manipulation
                start_datetime = datetime.strptime(f"{date_str} {start_times[i]}", "%d-%m-%Y %H:%M")
                end_datetime = datetime.strptime(f"{date_str} {end_times[i]}", "%d-%m-%Y %H:%M")
                start_break_datetime = datetime.strptime(f"{date_str} {start_break_times[i]}", "%d-%m-%Y %H:%M")
                end_break_datetime = datetime.strptime(f"{date_str} {end_break_times[i]}", "%d-%m-%Y %H:%M")
                
                # First part of the day (before break)
                current_slot = start_datetime
                while current_slot + timedelta(minutes=avg_appointment_duration) <= start_break_datetime:
                    all_slots.append(current_slot)
                    current_slot = current_slot + timedelta(minutes=avg_appointment_duration)
                
                # Second part of the day (after break)
                current_slot = end_break_datetime
                while current_slot + timedelta(minutes=avg_appointment_duration) <= end_datetime:
                    all_slots.append(current_slot)
                    current_slot = current_slot + timedelta(minutes=avg_appointment_duration)
            except Exception as e:
                logger.warning(f"Error processing time slot {i}: {str(e)}")
                continue
        
        # Filter out unavailable slots
        available_slots = []
        for slot in all_slots:
            if slot not in unavailable_slots:
                available_slots.append(slot.strftime("%H:%M"))

        # Extract working addresses properly
        working_address = doctor.get('work_address', [])
            
        # Create response with all working hours
        working_hours_array = []
        for i in range(len(start_times)):
            working_hours_array.append({
                "start_time": start_times[i],
                "end_time": end_times[i],
                "break_time": {
                    "start": start_break_times[i],
                    "end": end_break_times[i]
                }
            })
        
        # Sort available slots by time
        available_slots.sort()
        
        available_dict = {
            "CIN": CIN,
            "date": date_str,
            "working_hours": working_hours_array[0] if working_hours_array else {},  # Keep first one for backward compatibility
            "all_working_hours": working_hours_array,  # Include all working hours
            "working_days": [day.capitalize() for day in working_days] if working_days else [],
            "holidays": [day.capitalize() for day in holidays] if holidays else [],
            "working_address": working_address,
            "avg_appointment_duration": avg_appointment_duration,
            "available_slots": available_slots
        }
        
        # Cache the result
        await set_appointment_slot(CIN, date_str, available_dict)

        return available_dict
    
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error fetching available slots: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error fetching available slots: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")
        
@patient_book.get("/refresh/available_slots/{CIN}/{date}", status_code=status.HTTP_200_OK)
async def refresh_available_slots(CIN: str, date: str):
    try:
        await client.delete(f"appointment_available_slot:{date}:{CIN}")
        logger.info(f"Cache cleared for available slots: {CIN} on {date}")
        create_new_log("info", f"Cache cleared for available slots: {CIN} on {date}", "/api/backend/Appointment")
        return {"message": "Cache cleared successfully", "status": status.HTTP_200_OK}
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error refreshing available slots: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error refreshing available slots: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")


@patient_book.get("/patient/get/busy_date/{CIN}", status_code=status.HTTP_200_OK)
async def get_busy_dates_api(CIN: str):
    try:
        # Check cache first
        cache_data = await get_busy_date(CIN)
        if cache_data:
            print("data from cache")
            logger.info(f"Cache hit for busy dates: {CIN}")
            create_new_log("info", f"Cache hit for busy dates: {CIN}", "/api/backend/Appointment")
            return cache_data
        print("data from database")
        # Get doctor details
        doctor = await conn.public_profile_data.doctor.find_one({"CIN": CIN})
        if not doctor:
            logger.error(f"Doctor not found with CIN: {CIN}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

        # Calculate date range for next 3 months
        today = datetime.now().date()
        # print("today", today)
        end_date = today + timedelta(days=90)  # Approximately 3 months
        # print("end_date", end_date)
        
        # Convert dates to string format for comparison
        today_str = today.strftime("%d-%m-%Y")
        # print("today_str", today_str)
        end_date_str = end_date.strftime("%d-%m-%Y")
        # print("end_date_str", end_date_str)

        # Get all existing appointments for the doctor within the next 3 months
        # REMOVED status filter to include ALL appointments for debugging
        appointments = await conn.booking.appointment.find({"CIN": CIN}).to_list(length=None)
        if not appointments:
            logger.warning(f"No appointments found for doctor: {CIN}")
            result = {
                "CIN": CIN, 
                "busy_dates": [], 
                "date_range": {"from": today_str, "to": end_date_str},
                "message": "No appointments found",
                "debug_doctor_keys": list(doctor.keys())
            }
            await set_busy_date(CIN, result)
            return result
        print("total appointments",len(appointments))
        print(f"Found {len(appointments)} total appointments for doctor {CIN}")

        filtered_appointments = []
        for a in appointments:
            try:
                appt_date = datetime.strptime(a["appointment_date"], "%d-%m-%Y").date()
                if today <= appt_date <= end_date:
                    filtered_appointments.append(a)
            except Exception as e:
                print(f"Invalid date in record: {a.get('appointment_date')} -> {e}")

        # Extract doctor's working schedule
        working_time = doctor.get('working_time', [])
        # print("working_time", working_time)
        
        if not working_time:
            logger.warning(f"No working time found for doctor: {CIN}")
            result = {
                "CIN": CIN, 
                "busy_dates": [], 
                "date_range": {"from": today_str, "to": end_date_str},
                "message": "No working time configured",
                "debug_doctor_keys": list(doctor.keys())
            }
            await set_busy_date(CIN, result)
            return result

        # Extract working days - Multiple strategies
        working_days = working_time[0].get('working_days', [])
        print("working_days", working_days)
        # print("working days", working_time)['working days']
        # Strategy 1: Direct working_days field
        if working_days:
            print("inside working days")
            raw_working_days = working_days
            # print(f"Raw working_days field: {raw_working_days}")
            
            if isinstance(raw_working_days, list):
                # print("print inside list")
                working_days = [day.lower().strip() for day in raw_working_days if day]
                # print("after update", working_days)
            elif isinstance(raw_working_days, str):
                # print("print inside string")
                # Handle comma-separated string
                working_days = [day.lower().strip() for day in raw_working_days.split(',') if day.strip()]
        
        # Strategy 2: From your image data structure - handle nested structure
        if not working_days:
            # Based on your image, it seems like working_days might be nested deeper
            # Let's try to find it in various places
            for key in doctor.keys():
                print(f"Checking key: {key}")
                if 'working' in key.lower() or 'days' in key.lower():
                    # print(f"Found potential working days field '{key}': {doctor[key]}")
                    
                    value = doctor[key]
                    if isinstance(value, list) and len(value) > 0:
                        # Check if it's a list of day names
                        if all(isinstance(item, str) for item in value):
                            working_days = [day.lower().strip() for day in value]
                            break
                        # Check if it's a list of objects containing days
                        elif all(isinstance(item, dict) for item in value):
                            for item in value:
                                if 'days' in item:
                                    working_days.extend([day.lower().strip() for day in item['days']])
        
        print(f"Final working days for doctor {CIN}: {working_days}")
        
        # Get average appointment duration
        avg_appointment_duration = int(doctor.get('avg_appointment_duration', None))  # Default 30 minutes
        print(f"Average appointment duration: {avg_appointment_duration}")
        
        # Get holidays (array of date strings)
        holidays = working_time[0].get('holidays', [])
        # print("doctor", doctor)
        print(f"Holidays: {holidays}")

        def calculate_available_slots_per_day():
            """Calculate total available appointment slots per working day"""
            total_minutes = 0
            
            print(f"Calculating slots from working_time: {working_time}")
            
            for work_schedule in working_time:
                # print(f"Processing work schedule: {work_schedule}")
                
                # Parse start and end times
                start_times = work_schedule.get('start_time', [])
                end_times = work_schedule.get('end_time', [])
                start_break_times = work_schedule.get('start_break_time', [])
                end_break_times = work_schedule.get('end_break_time', [])
                
                # print(f"Start times: {start_times}, End times: {end_times}")
                # print(f"Break start: {start_break_times}, Break end: {end_break_times}")
                # print("len" ,len(start_times), len(end_times), len(start_break_times), len(end_break_times))
                
                # Calculate working minutes for each time slot
                for i in range(len(start_times)):
                    if i < len(end_times):
                        try:
                            start_time = datetime.strptime(start_times[i], "%H:%M")
                            end_time = datetime.strptime(end_times[i], "%H:%M")
                            
                            # Calculate total work minutes
                            work_minutes = (end_time - start_time).total_seconds() / 60
                            print(f"Work minutes for slot {i}: {work_minutes}")
                            
                            # Subtract break time if exists
                            if (i < len(start_break_times) and i < len(end_break_times) and 
                                start_break_times[i] and end_break_times[i]):
                                start_break = datetime.strptime(start_break_times[i], "%H:%M")
                                end_break = datetime.strptime(end_break_times[i], "%H:%M")
                                break_minutes = (end_break - start_break).total_seconds() / 60
                                work_minutes -= break_minutes
                                print(f"After subtracting {break_minutes} break minutes: {work_minutes}")
                            
                            total_minutes += max(0, work_minutes)  # Ensure no negative minutes
                            print(f"Total minutes after slot {i}: {total_minutes}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Error parsing time for doctor {CIN}: {str(e)}")
                            continue
            
            print(f"Total working minutes: {total_minutes}")
            # Calculate number of appointment slots
            slots = int(total_minutes // avg_appointment_duration) if avg_appointment_duration > 0 else 0
            print(f"Calculated slots per day: {slots}")
            return slots

        def get_day_name(date_str):
            """Convert date string to day name"""
            try:
                # Try different date formats
                for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                    try:
                        date_obj = datetime.strptime(date_str, fmt)
                        day_name = date_obj.strftime("%A").lower()
                        print(f"Date {date_str} is {day_name}")
                        return day_name
                    except ValueError:
                        continue
                logger.warning(f"Could not parse date: {date_str}")
                return None
            except Exception as e:
                logger.error(f"Error getting day name for {date_str}: {str(e)}")
                return None

        def is_date_in_range(date_str):
            """Check if date is within the next 3 months"""
            try:
                for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                    try:
                        date_obj = datetime.strptime(date_str, fmt).date()
                        in_range = today <= date_obj <= end_date
                        # print(f"Date {date_str} in range: {in_range}")
                        return in_range
                    except ValueError:
                        continue
                logger.warning(f"Could not parse date for range check: {date_str}")
                return False
            except Exception as e:
                logger.error(f"Error checking date range for {date_str}: {str(e)}")
                return False

        # Calculate available slots per day
        max_slots_per_day = calculate_available_slots_per_day()
        
        if max_slots_per_day == 0:
            logger.warning(f"No available slots calculated for doctor: {CIN}")
            result = {
                "CIN": CIN, 
                "busy_dates": [],
                "max_slots_per_day": 0,
                "total_busy_dates": 0,
                "working_days": working_days,
                "date_range": {"from": today_str, "to": end_date_str},
                "message": "No available appointment slots configured, error in doctor schedule",
            }
            await set_busy_date(CIN, result)
            return result

        # Group filtered_appointments by date (only for dates within range)
        appointments_by_date = defaultdict(int)
        valid_appointments = 0
        
        for appointment in filtered_appointments:
            appointment_date = appointment.get('appointment_date')
            appointment_status = appointment.get('status')
            
            # print(f"Processing appointment: date={appointment_date}, status={appointment_status}")
            
            if appointment_date and is_date_in_range(appointment_date):
                # For now, count all filtered_appointments regardless of status for debugging
                appointments_by_date[appointment_date] += 1
                valid_appointments += 1
                # print(f"Counted appointment for date: {appointment_date}")

        print(f"Valid filtered_appointments within range: {valid_appointments}")
        print(f"Appointments by date: {dict(appointments_by_date)}")

        # Find busy dates within the next 3 months
        busy_dates = []
        
        for date, appointment_count in appointments_by_date.items():
            print(f"Processing date: {date} with {appointment_count} filtered_appointments")
            
            # Skip if date is a holiday
            if date in holidays:
                print(f"Skipping holiday date: {date}")
                continue
            
            # Check if date falls on a working day
            day_name = get_day_name(date)
            
            if not day_name:
                logger.warning(f"Could not determine day name for date: {date}")
                continue
                
            print(f"Date {date} is {day_name}, checking against working days: {working_days}")
            
            if day_name not in working_days:
                print(f"Skipping non-working day: {date} ({day_name})")
                continue
            
            # Check if filtered_appointments equal or exceed available slots
            print(f"Comparing {appointment_count} filtered_appointments vs {max_slots_per_day} max slots")
            if appointment_count >= max_slots_per_day:
                busy_dates.append(date)
                logger.info(f"BUSY DATE FOUND: {date} ({appointment_count}/{max_slots_per_day} slots)")

        # Sort busy dates
        def sort_date(date_str):
            """Sort key function for dates"""
            for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            return datetime.min  # Fallback for unparseable dates

        try:
            busy_dates.sort(key=sort_date)
        except Exception:
            busy_dates.sort()  # Fallback to string sort


        #  get day name for busy dates as well
        busy_dates_with_day_name = []
        for date in busy_dates:
            day_name = get_day_name(date)
            if day_name:
                busy_dates_with_day_name.append(day_name)
        print(f"Busy dates with day names: {busy_dates_with_day_name}")

        # Prepare result
        result = {
            "CIN": CIN,
            "busy_dates": busy_dates,
            "busy_days_name": busy_dates_with_day_name,
            "max_slots_per_day": max_slots_per_day,
            "total_busy_dates": len(busy_dates),
            "working_days": working_days,
            "total_holidays": len(holidays),
            "holidays": holidays,
            "date_range": {
                "from": today_str,
                "to": end_date_str
            },
            "appointments_by_date": dict(appointments_by_date)
        }
        
        # Cache the result
        await set_busy_date(CIN, today_str, result)

        logger.info(f"Successfully calculated busy dates for doctor {CIN} for next 3 months: {len(busy_dates)} busy dates found")
        create_new_log("info", f"Successfully calculated busy dates for doctor {CIN} for next 3 months: {len(busy_dates)} busy dates", "/api/backend/Appointment")
        
        return result
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error fetching busy dates: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error fetching busy dates: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")


@patient_book.get("/refresh/get_busy_date/{CIN}", status_code=status.HTTP_200_OK)
async def refresh_busy_dates(CIN: str):
    try:
        # Get all keys that match the pattern
        cache_keys = await client.keys(f"busy_date:{CIN}:*")
        
        if cache_keys:
            await client.delete(*cache_keys)  # Unpack and delete all matching keys
            create_new_log("info", f"Deleted cached busy dates for CIN {CIN}", "/api/backend/Appointment")
            logger.info(f"Deleted {len(cache_keys)} cached busy dates for CIN {CIN}")
            return {
                "message": f"Deleted {len(cache_keys)} cached busy dates for CIN {CIN}",
                "status_code": status.HTTP_200_OK
            }
        else:
            return {
                "message": f"No cached busy dates found for CIN {CIN}",
                "status_code": status.HTTP_404_NOT_FOUND
            }

    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error deleting cached busy dates: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error deleting cached busy dates: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))



@patient_book.get("/patient/previous_appointments/{email}", status_code=status.HTTP_200_OK)
async def patient_get_previous_appoitment(email: str):
    try:
        cache_keys = await client.keys(f"appointment:{email}:*")
        if cache_keys:
            print("Cache data found")
            cached_appointments = []
            for key in cache_keys:
                appointment_data = await client.hgetall(key)
                if appointment_data:
                    cached_appointments.append(appointment_data)
            return cached_appointments
        
        print("No cache data found") #debugging
        appointments =  await conn.booking.temp_appointment.find({"email": email}).sort([("appointment_date", 1), ("appointment_time", 1)]).to_list(length=None)
        print(appointments) #debugging
        appo = []
        for appointment in appointments:
            appointment_data = {
                "doctor_name": appointment["doctor_name"],
                "appointment_date": appointment["appointment_date"],
                "appointment_time": appointment["appointment_time"],
                "status": appointment["status"],
                "appointment_id": appointment["appointment_id"],
                "CIN": appointment["CIN"],
                "number_of_appointments": appointment["number_of_appointments"]
            }
            appo.append(appointment_data)
            
            # Cache the appointment
            await client.hset(f"previous_appointment:{email}:{appointment['_id']}", mapping=appointment_data)
            await client.expire(f"previous_appointment:{email}:{appointment['_id']}", 3600)
        return appo
    
    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error fetching appointments: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error fetching appointments: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")
    

@patient_book.get("/patient/refresh/previous_appointments/{email}", status_code=status.HTTP_200_OK)
async def refresh_previous_appointments(email: str):
    try:
        # Get all keys that match the pattern
        cache_keys = await client.keys(f"previous_appointment:{email}:*")
        
        if cache_keys:
            await client.delete(*cache_keys)  # Unpack and delete all matching keys
            create_new_log("info", f"Deleted cached previous appointments for email {email}", "/api/backend/Appointment")
            logger.info(f"Deleted {len(cache_keys)} cached previous appointments for email {email}")
            return {
                "message": f"Deleted {len(cache_keys)} cached previous appointments for email {email}",
                "status_code": status.HTTP_200_OK
            }
        else:
            return {
                "message": f"No cached previous appointments found for email {email}",
                "status_code": status.HTTP_404_NOT_FOUND
            }

    except Exception as e:
        formatted_error = traceback.format_exc()
        create_new_log("error", f"Error deleting cached previous appointments: {formatted_error}", "/api/backend/Appointment")
        logger.error(f"Error deleting cached previous appointments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
