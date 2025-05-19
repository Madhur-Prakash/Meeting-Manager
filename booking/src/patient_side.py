from fastapi import APIRouter, HTTPException, status
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")
from models import models
import traceback
from booking.config.redis_config import client
from ..helper.utils import setup_logging, cache_appointment, get_cached_appointments, insert_in_db, delete_cached_appointment, send_email, send_email_ses, create_new_log, set_appointment_slot, get_appointment_slot
from ..config.database import conn

patient_book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

logger = setup_logging() # initialize logger


@patient_book.get("/patient/appointment/{email}", status_code=status.HTTP_200_OK)
async def get_all(email: str):
    try:
        appointments =  await conn.booking.appointment.find({"email": email}).sort([("appointment_date", 1), ("appointment_time", 1)]).to_list(length=None)
        print(appointments) #debugging
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
        appo = []
        for appointment in appointments:
            appointment_data = {
                "doctor_name": appointment["doctor_name"],
                "appointment_date": appointment["appointment_date"],
                "appointment_time": appointment["appointment_time"]
            }
            appo.append(appointment_data)
            
            # Cache the appointment
            await client.hset(
                f"appointment:{email}:{appointment['_id']}", mapping=appointment_data)
        
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
            create_new_log("info", f"Deleted cached appointments for CIN {email}", "/api/backend/Appointment")
            logger.info(f"Deleted cached appointments for CIN {email}")
            return {"message": f"Deleted {len(cache_keys)} cached appointments for CIN {email}", "status_code": status.HTTP_200_OK}
        else:
            return {"message": f"No cached appointments found for CIN {email}", "status_code": status.HTTP_404_NOT_FOUND}
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
        # print(doctor['work_address']) #debugging
        # Get doctor's working time configuration
        try:
            avg_appointment_duration = int(doctor['avg_appointment_duration'])  # in minutes
            
            if 'working_time' not in doctor or not doctor['working_time']:
                raise KeyError("Working time not configured for doctor")
                
            working_time = doctor['working_time'][0]  # Get the first element of the working_time array
            
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
            
            # Extract time information
            start_time = working_time['start_time']
            end_time = working_time['end_time']
            start_break_time = working_time['start_break_time']
            end_break_time = working_time['end_break_time']
            
        except (KeyError, IndexError, ValueError) as e:
            logger.error(f"Invalid doctor schedule configuration: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Invalid doctor schedule configuration: {str(e)}"
            )
        
        # Convert string times to datetime objects for easier manipulation
        start_datetime = datetime.strptime(f"{date_str} {start_time}", "%d-%m-%Y %H:%M")
        end_datetime = datetime.strptime(f"{date_str} {end_time}", "%d-%m-%Y %H:%M")
        start_break_datetime = datetime.strptime(f"{date_str} {start_break_time}", "%d-%m-%Y %H:%M")
        end_break_datetime = datetime.strptime(f"{date_str} {end_break_time}", "%d-%m-%Y %H:%M")
        
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
        
        # Generate all possible time slots based on working hours and appointment duration
        all_slots = []
        
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
        
        # Filter out unavailable slots
        available_slots = []
        for slot in all_slots:
            if slot not in unavailable_slots:
                available_slots.append(slot.strftime("%H:%M"))

        working_address = []
        for address in doctor['work_address']:
            working_address.append(address)
            
        # Create response
        available_dict = {
            "CIN": CIN,
            "date": date_str,
            "working_hours": {
                "start_time": start_time,
                "end_time": end_time,
                "break_time": {
                    "start": start_break_time,
                    "end": end_break_time
                }
            },
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