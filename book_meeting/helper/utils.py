import json
import random
import smtplib
import string
import logging
import os
from book_meeting.models.models import CustomJSONEncoder
from ..config.redis_config import client
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
    logger = logging.getLogger("meeting_log") # create logger
    if not logger.hasHandlers(): # check if handlers already exist
        logger.setLevel(logging.INFO) # set log level

        # create log directory if it doesn't exist
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)

        # create a file handler
        file_handler = ConcurrentRotatingFileHandler(
            os.path.join(log_dir, "meeting.log"), 
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

logger = setup_logging()

rand_numbers = set()

def  random_number():
    digits = string.digits
    meeting_id = ''.join(random.choice(digits) for i in range(6))
    if meeting_id not in rand_numbers:
        rand_numbers.add(meeting_id)
        return meeting_id
    else:
        return random_number()

async def cache_meeting(data: dict):
    meeting_key = f"meeting:{data['meeting_date']}:{data['UID']}:{data['meeting_id']}"
    await client.hset(meeting_key, mapping={
        "full_name": data['full_name'],
        "meeting_date": data['meeting_date'],
        "meeting_time": data['meeting_time'],
        "UID": data['UID'],
        "status": data['status'],
        "meeting_id": data['meeting_id']
    })
    await client.expire(meeting_key, 8 * 24 * 60 * 60)  # Cache for 7 days
    print("Meeting cached successfully")

async def get_cached_meetings(data: dict):
    keys = await client.keys(f"meeting:{data['meeting_date']}:{data['UID']}*")
    # print(keys) #debugging
    meetings = []
    for key in keys:
        cached_data = await client.hgetall(key)
        if cached_data:
            meetings.append(cached_data)
    if meetings:
        # print(meetings) #debugging
        print("Meetings fetched from cache")
        return meetings
    return None

async def delete_cached_meeting(data: dict):
    keys = await client.keys(f"meeting:{data['meeting_date']}:{data['UID']}:{data['meeting_id']}")
    for key in keys:
        await client.delete(key)
    print("Meeting deleted from cache")
    return 0

async def insert_in_db(form: dict):
            form["meeting_id"] = random_number() # generate random meeting id
            form["status"] = "false" # set status to false

            new_meeting = await conn.booking.meeting.insert_one(form)
            count_doc = await conn.booking.meeting.count_documents({
                "full_name": form["full_name"],
                "UID": form["UID"],
                "meeting_date": form["meeting_date"]
            })
            await conn.booking.meeting.update_one({
                "_id": new_meeting.inserted_id
            }, {
                "$set": {
                    "number_of_meetings": count_doc
            }}) 

            
            if not new_meeting.inserted_id:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to book meeting")
            print("Meeting booked successfully") #debugging
            # data caching after all the validation are done and meeting is booked
            await cache_meeting(form)
            return (form)


async def set_meeting_slot(UID: str, date: str, form: dict):
    meeting_key = f"meeting_available_slot:{form['date']}:{form['UID']}"
    redis_data = {k: json.dumps(v, cls=CustomJSONEncoder) if isinstance(v, (dict, list)) else v 
                      for k, v in form.items()}
    await client.hset(meeting_key, mapping=redis_data)
    await client.expire(meeting_key, 8 * 24 * 60 * 60)  # Cache for 7 days
    logger.info(f"Meeting slot cached successfully for {UID} on {date}")
    print("Free meeting slot cached successfully")


async def get_meeting_slot(date: str, UID: str):
    meeting_key = f"meeting_available_slot:{date}:{UID}"
    cached_data = await client.hgetall(meeting_key)
    if cached_data:
        print("Meeting slots fetched from cache")
        return {
            "UID": cached_data["UID"],
            "date": cached_data["date"],
            "working_hours": json.loads(cached_data["working_hours"]),
            "working_days": json.loads(cached_data["working_days"]),
            "holidays": json.loads(cached_data["holidays"]),
            "working_address": json.loads(cached_data["working_address"]),
            "avg_meeting_duration":cached_data["avg_meeting_duration"],
            "available_slots": json.loads(cached_data["available_slots"])
        }
    else:
        print("No meeting slots available in cache")
        return None
    
async def get_busy_date(UID: str):
    pattern = f"busy_date:{UID}:*"
    try:
        keys = await client.keys(pattern)
        if not keys:
            return None

        key = keys[0]
        cached_data = await client.hgetall(key)
        if not cached_data:
            return None

        result = {}
        for k, v in cached_data.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result
    except Exception as e:
        logger.error(f"Error getting cached busy date: {str(e)}")
        return None



async def set_busy_date(UID: str, today: str, form: dict):
    """Cache busy date data"""
    key = f"busy_date:{UID}:{today}"
    try:
        redis_data = {k: json.dumps(v, cls=CustomJSONEncoder) if isinstance(v, (dict, list)) else str(v)
                      for k, v in form.items()}
        await client.hset(key, mapping=redis_data)
        await client.expire(key, 8 * 24 * 60 * 60)  # Cache for 8 days
        print("Busy date cached successfully")
        logger.info(f"Busy date cached successfully for {UID}")
    except Exception as e:
        logger.error(f"Error caching busy date: {str(e)}")


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

def send_mail_to_mailhog(to_email, subject, body, retries=3, delay=5):
    """Send an email using MailHog (local SMTP server) with retry mechanism."""
    for attempt in range(retries):
        try:
            msg = MIMEText(body, "html")
            msg["Subject"] = subject
            msg["From"] = NO_REPLY_EMAIL
            msg["To"] = to_email

            with smtplib.SMTP("localhost", 1025) as server:
                server.sendmail(NO_REPLY_EMAIL, [to_email], msg.as_string())

            print(f"Email sent to {to_email} via MailHog!")
            return {"status": "success", "to": to_email}
        except Exception as e:
            print(f"Failed to send email to MailHog: {e}. Retrying in {delay} seconds...")
            print(f"Error: {traceback.format_exc()}")
            time.sleep(delay)
            return {"status": "failure", "error": str(e)}

    print("Failed to send email to MailHog after multiple attempts.")


def create_new_log(log_type: str, message: str, head: str):
    url ="http://127.0.0.1:8000/backend/create_new_logs"
    log = {
         "log_type": log_type,
         "message": message}
    headers = {
        "X-Source-Endpoint": head}
            
    resp = requests.post(url, json=log, headers=headers)
    return resp