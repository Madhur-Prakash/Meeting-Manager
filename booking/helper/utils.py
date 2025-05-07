import random
import string
import logging
import os
from ..config.redis import client
import traceback
import base64
import pickle
import requests
import time
# from .celery_app import celery
import os
from dotenv import load_dotenv
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from ..config.database import conn
from fastapi import HTTPException, status
from concurrent_log_handler import ConcurrentRotatingFileHandler

load_dotenv()

NO_REPLY_EMAIL = os.getenv("NO_REPLY_EMAIL")

# Define the scope for Gmail API
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

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

def authenticate_gmail():
    """Authenticate and return Gmail API service."""
    creds = None

    # Load credentials from token.pickle if available
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    # If credentials are invalid or don't exist, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for future use
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("gmail", "v1", credentials=creds)

# @celery.task()
def send_email(to_email, subject, body, retries=3, delay=5):
    """Send an email using Gmail API with retry mechanism."""
    for attempt in range(retries):
        try:
            service = authenticate_gmail()

            # Create email message
            message = MIMEText(body, "html")  # Specify the MIME type as "html"
            message["to"] = to_email
            message["subject"] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # Send email using Gmail API
            message = {"raw": raw_message}
            sent_message = service.users().messages().send(userId="me", body=message).execute()
            print(f"Email sent! Message ID: {sent_message['id']}")
            return sent_message
        except Exception as e:
            print(f"Failed to send email due to timeout: {e}. Retrying in {delay} seconds...")
            print(f"Error: {traceback.format_exc()}")
            time.sleep(delay)
    print("Failed to send email after multiple attempts.")


# @celery.task()
def send_email_ses(to_email, subject, body, retries=3, delay=5):
    """Send an email using AWS SES with retry mechanism."""
    for attempt in range(retries):
        try:
            response = client.send_email(
                Source=NO_REPLY_EMAIL,  # Must be a verified email in AWS SES
                Destination={
                    "ToAddresses": [to_email]  # Ensure it's a LIST
                },
                Message={
                    "Subject": {"Data": subject},
                    "Body": {
                        "Html": {"Data": body}
                    }
                }
            )
            print(f"Email sent! Message ID: {response['MessageId']}")
            return response
        except Exception as e:
            print(f"Failed to send email due to error: {e}. Retrying in {delay} seconds...")
            print(f"Error: {traceback.format_exc()}")
            time.sleep(delay)

def create_new_log(log_type: str, message: str, head: str):
    url ="http://127.0.0.1:8000/backend/create_new_logs"
    log = {
         "log_type": log_type,
         "message": message}
    headers = {
        "X-Source-Endpoint": head}
            
    resp = requests.post(url, json=log, headers=headers)
    return resp