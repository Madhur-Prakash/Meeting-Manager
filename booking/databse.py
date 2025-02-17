from pymongo import MongoClient
MONGO_URI = "mongodb://ec2-3-84-251-0.compute-1.amazonaws.com:27017"

# connect to MongoDB
conn = MongoClient(MONGO_URI)