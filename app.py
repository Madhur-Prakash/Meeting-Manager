from fastapi import FastAPI
from booking.book import book
from booking.doctor_side import doc

app=FastAPI()
app.include_router(book)
app.include_router(doc)
