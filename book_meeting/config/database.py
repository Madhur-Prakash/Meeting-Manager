from motor.motor_asyncio import AsyncIOMotorClient

# MONGO_URI = "mongodb://ec2-98-80-166-39.compute-1.amazonaws.com:27017/auth"  # --> for aws testing

MONGO_URI = "mongodb://localhost:27017" # --> for local testing

# connect to MongoDB
conn = AsyncIOMotorClient(MONGO_URI)