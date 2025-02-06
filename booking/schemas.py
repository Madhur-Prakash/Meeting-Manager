

def Booking(item) -> dict:
    return{
        "doctor_name": item["doctor_name"],
        "patient_name": item["patient_name"],
        "email": item["email"],
        "appointment_date": item["appointment_date"],
        "appointment_time": item["appointment_time"]
    }

def user(item) -> dict:
    return {
        "_id": str(item["_id"]),
        "full_name": item["full_name"],
        "user_name": item["user_name"],
        "email": item["email"],
        "password": item["password"],
        "password2": item["password2"],
        "phone_number": item["phone_number"],
        "disabled": item.get("disabled", False)
    }
        

def userEntity(item) -> list:
    return[user(item) for item in item] 

def BookingEntity(item) -> list:
    return [Booking(item) for item in item]