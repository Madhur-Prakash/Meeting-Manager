import aioredis

# redis connection
# client = aioredis.from_url('redis://default@54.162.195.191:6379', decode_responses=True) #in production

client =  aioredis.from_url('redis://localhost', decode_responses=True) # in local testing