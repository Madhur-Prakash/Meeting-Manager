

def Booking(item) -> dict:
    return{
        "doctor_name": item["doctor_name"],
        "patient_name": item["patient_name"],
        "email": item["email"],
        "appointment_date": item["appointment_date"],
        "appointment_time": item["appointment_time"]
    }

def BookingEntity(item) -> list:
    return [Booking(item) for item in item]