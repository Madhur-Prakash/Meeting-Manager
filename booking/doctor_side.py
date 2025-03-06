from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import aioredis
import asyncio
from datetime import datetime, timedelta
from .utils import setup_logging, cache_appointment, delete_cached_appointment, insert_in_db,send_email
import traceback
from .database import conn

doctor_book = APIRouter()

templates = Jinja2Templates(directory="booking/templates")

logger = setup_logging() # initialize logger

# redis connection
# client = aioredis.from_url('redis://default@54.87.254.150:6379', decode_responses=True) #in production

client =  aioredis.from_url('redis://localhost', decode_responses=True) # in local testing

@doctor_book.get("/doctor/{CIN}", response_class=HTMLResponse)
async def get_all(request: Request, CIN: str):
    try:
        appointments =  await conn.booking.appointment.find({"CIN": CIN}).sort([("appointment_date", 1), ("appointment_time", 1)]).to_list(length=None)
        print(appointments) #debugging
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
        
        return templates.TemplateResponse("doc.html", {"request": request, "appointments": appo})
    
    except Exception as e:
        print(traceback.format_exc())
        logger.error(f"Error fetching appointments: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    
@doctor_book.post("/doctor/appointment/reschedule/{appointment_id}", status_code=status.HTTP_302_FOUND)
async def reschedule(request: Request, appointment_id: str):
    try:
        form_data = await request.json()
        new_appointment_date = form_data["appointment_date"]
        new_appointment_time = form_data["appointment_time"]
        reason = form_data["reason"]

        #  required fields
        if not new_appointment_date or not new_appointment_time or not reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All fields are required")

        new_appointment_datetime = datetime.strptime(f"{new_appointment_date} {new_appointment_time}", "%Y-%m-%d %H:%M")
        
        # Check if the new appointment date is in the past
        # if new_appointment_datetime < datetime.now().isoformat():
        #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Appointment date cannot be in the past")

        existing_appointment = await conn.booking.appointment.find_one({"appointment_id": appointment_id})
        if not existing_appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        # Check if the slot is already booked
        if(existing_appointment['appointment_date'] == new_appointment_date and existing_appointment['appointment_time'] == new_appointment_time):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment slot is already booked. Please choose a different time.")

        existing_appointment_time = await conn.booking.appointment.find({
            "appointment_date": new_appointment_date}).to_list(length=None)
        print("existing_appointment_time", existing_appointment_time)
        for existing_appo_time in existing_appointment_time:
            existing_time = datetime.strptime(f"{existing_appo_time['appointment_date']} {existing_appo_time['appointment_time']}", "%Y-%m-%d %H:%M")

            # Check if new appointment is within 30 minutes before or after an existing appointment
            if abs(existing_time - new_appointment_datetime) < timedelta(minutes=30):
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
                {"appointment_id": appointment_id},
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
                "appointment_id": appointment_id}
            
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

            sent_mail = asyncio.create_task(send_email(existing_appointment["email"], "Appointment Reschedule Confirmation", html_body, retries=3, delay=5))
            if not sent_mail:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send email. Please try again later.")


            logger.info(f"Appointment rescheduled successfully: {appointment_id}")
            return {"message": "Appointment rescheduled successfully", "appointment_id": appointment_id, "status": status.HTTP_200_OK}

        # If the date has changed, update the number of appointments for the old date
        elif new_appointment_date != existing_appointment['appointment_date']:
            #  delete the old appointment from the database
            await conn.booking.appointment.delete_one({"appointment_id": appointment_id})

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

            sent_mail = asyncio.create_task(send_email(existing_appointment["email"], "Appointment Reschedule Confirmation", html_body, retries=3, delay=5))
            if not sent_mail:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send email. Please try again later.")

            new_appointment = await insert_in_db(updated_mongo_doc)
            logger.info(f"Appointment rescheduled successfully: {new_appointment['appointment_id']}")
            return {"message": "Appointment rescheduled successfully", "appointment_id": new_appointment['appointment_id'], "status": status.HTTP_200_OK}
    
#****************************************************************************************************************************************************
    except Exception as e:
        logger.error(f"Error rescheduling appointment: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")
    
@doctor_book.post("/doctor/appointment/done/{appointment_id}", status_code=status.HTTP_302_FOUND)
async def done_appointment(request: Request, appointment_id: str):
    try:
        form_data = await request.json()
        status = form_data["status"]

        existing_appointment = await conn.booking.appointment.find_one({"appointment_id": appointment_id})
        if not existing_appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
        
        await conn.booking.appointment.update_one({"appointment_id": appointment_id}, {"$set": {"status": status}})
        await conn.booking.appointment.delete_one({"appointment_id": appointment_id})
        logger.info(f"Appointment status updated successfully: {appointment_id}")
        return {"message": "Appointment status updated successfully", "appointment_id": appointment_id, "status": status}
    except Exception as e:
        logger.error(f"Error updating appointment status: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")