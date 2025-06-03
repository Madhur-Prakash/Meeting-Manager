from fastapi import FastAPI
from book_meeting.src.meeting import meet
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI()
app.include_router(meet)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
