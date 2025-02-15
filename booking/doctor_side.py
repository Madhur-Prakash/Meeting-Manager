from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import aioredis
from .databse import conn

doc = APIRouter()

templates = Jinja2Templates(directory="booking/templates")
client = aioredis.from_url('redis://localhost', decode_responses=True)

async def cache(data: dict):
    pass

@doc.get("/doctor/{user_name}", response_class=HTMLResponse)
async def get_all(request: Request, user_name: str):
    try:
        appointments = conn.booking.appointment.find({"user_name": user_name}).sort([("appointment_date", 1), ("appointment_time", 1)])
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
                f"appointment:{user_name}:{appointment['_id']}", mapping=appointment_data)
        
        return templates.TemplateResponse("doc.html", {"request": request, "appointments": appo})
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=str(e)
        )