from fastapi import FastAPI
from booking.book import book
from fastapi.staticfiles import StaticFiles

app=FastAPI()
app.include_router(book)
