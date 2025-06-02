# Appointment Booking System
## Overview
This FastAPI practice project is designed for a doctor-patient appointment booking system. The system allows patients to book appointments, reschedule, or cancel existing ones. Both doctors and patients can view their past and upcoming appointments. The system also features a caching mechanism for fast data transfer and calculates available appointment slots in advance for 90 days.

---

## Features
- **Appointment Booking**: Patients can book appointments with available time slots.
- **Rescheduling**: Both patients and doctors can reschedule appointments.
- **Cancellation**: Appointments can be canceled by either party.
- **Appointment History**: Doctors and patients can view their past and upcoming appointments.
- **Caching**: Applied for fast data transfer to improve system performance.
- **Advanced Slot Calculation**: Available appointment slots are calculated in advance for 90 days.

---

## Technology Stack
- **Backend Framework**: FastAPI
- **Database**: Managed through `database.py` in the `booking/config` directory
- **Caching**: Redis (configured in `redis_config.py`)
- **Programming Language**: Python

---

## Installation
1. Clone the repository:
   ```bash
   git clone git@github.com:Madhur-Prakash/appointment-booking.git
   ```
2. Navigate to the project directory:
   ```bash
   cd appointment-booking
   ```
3. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Configure the `.env` file as necessary for your environment.

---

## Usage
1. Start the FastAPI server:
   ```bash
   uvicorn app:app --reload
   ```
2. Access the API documentation at:
   ```
   http://127.0.0.1:8000/docs
   ```
3. Use the API to manage appointments, including booking, rescheduling, and cancellation.

---

## API Endpoints
API endpoints are accessible through the FastAPI application and can be found in the API documentation at `http://127.0.0.1:8000/docs`. Endpoints include but are not limited to:
- **POST /book-appointment**: Book a new appointment.
- **POST /reschedule-appointment**: Reschedule an existing appointment.
- **POST /cancel-appointment**: Cancel an appointment.
- **GET /appointments**: View all appointments (past and upcoming).

---

## Project Structure
```plaintext
appointment-booking/
├── .env
├── .gitignore  # gitignore file for GitHub
├── README.md  # Project documentation
├── __init__.py  # initializes package
├── app.py  # main FastAPI app
├── booking
│   ├── __init__.py  # initializes package
│   ├── config
│   │   ├── __init__.py  # initializes package
│   │   ├── celery_app.py
│   │   ├── database.py
│   │   └── redis_config.py
│   ├── helper
│   │   ├── __init__.py  # initializes package
│   │   └── utils.py
│   ├── models
│   │   ├── __init__.py  # initializes package
│   │   └── models.py  # models
│   ├── src
│   │   ├── __init__.py  # initializes package
│   │   └── meeting.py
│   ├── templates
│   │   ├── cached_appointment.html
│   │   ├── doc.html
│   │   └── index.html
│   └── test_api
│       ├── __init__.py  # initializes package
│       ├── api_hit.py
│       ├── fake_doctors.py
│       └── try_test.py
├── credentials.json
├── requirements.txt
└── token.pickle
```

---

## Future Enhancements
- Implement user authentication for doctors and patients.
- Add reminders for upcoming appointments.
- Integrate with calendar services for seamless scheduling.

---

## Contribution Guidelines
Contributions are welcome! To contribute:
1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Commit your changes and submit a pull request.

---

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Author
**Madhur-Prakash**  
[GitHub](https://github.com/Madhur-Prakash)