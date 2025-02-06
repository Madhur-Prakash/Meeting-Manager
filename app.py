from fastapi import FastAPI
from booking.book import book

app=FastAPI()
app.include_router(book)
