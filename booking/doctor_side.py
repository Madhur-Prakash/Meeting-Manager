from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import aioredis
from .databse import conn

doc = APIRouter()

templates = Jinja2Templates(directory="booking/templates")
client = aioredis.from_url('redis://localhost', decode_responses=True)

async def cache_doctor(data: dict):
    user_name = data["user_name"]
    keys = await client.keys(f"appointment:{user_name}:*")
    appointments = []
    for key in keys:
        cached_data = await client.hgetall(key)
        if cached_data:
            appointments.append(cached_data)
    if appointments:
        print("Appointments fetched from cache")
        return appointments
    return []

@doc.get("/{user_name}")
async def get_all(request: Request, user_name: str):
    # First, properly await the MongoDB cursor
    cursor = conn.booking.appointment.find({"doctor": user_name})
    # Then convert the cursor to a list
    appointments = await cursor.to_list(length=100)
    
    return templates.TemplateResponse(
        "doc.html",
        {"request": request, "appointments": appointments}
    )