# Meeting Scheduler

**A FastAPI-Based User-to-User Meeting Booking System**

## Overview
This FastAPI practice project implements a robust user-to-user meeting booking system. The system allows any user to book, reschedule, or cancel meetings with another user. It supports viewing both past and upcoming meetings, ensuring a comprehensive meeting management experience. The system includes a caching mechanism to enhance performance and precomputes available time slots for up to 90 days in advance, ensuring efficient scheduling and quick data retrieval.

---

## Features
- **User-to-User Meeting Booking**: Book meetings with other users.
- **Meeting Rescheduling**: Reschedule existing meetings as needed.
- **Meeting Cancellation**: Cancel meetings that are no longer required.
- **Past and Upcoming Meetings**: View both past and upcoming meetings for thorough meeting management.
- **Caching Mechanism**: Enhances performance by caching frequently accessed data.
- **Precomputed Time Slots**: Available time slots are precomputed for up to 90 days in advance for efficient scheduling.

---

## Technology Stack
- **Backend Framework**: FastAPI
- **Database**: MongoDB
- **Caching Mechanism**: Redis
- **Programming Language**: Python

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Madhur-Prakash/meeting-scheduler.git
   ```
2. Navigate to the project directory:
   ```bash
   cd meeting-scheduler
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
5. Set up MongoDB:
```bash
   # Install MongoDB and start the service.
   ```

6. Set up Redis:
```bash
   # Run this command to start Redis Stack in detached mode:
   docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 redis/redis-stack:latest
   # access Redis Stack at 👉 http://localhost:8001
   ```

7. Set up Mailhog:
```bash
   # Run this command to start Mailhog in detached mode:
   docker run -d --name mailhog -p 1025:1025 -p 8025:8025 mailhog/mailhog
   # access Mailhog at 👉 http://localhost:8025
```

8. Set up external logging service:
   - Clone the repository:
      ```bash
      git clone https://github.com/Madhur-Prakash/centralized-logging.git
      ```
   - Navigate to the project directory:
      ```bash
      cd centralized-logging
      ```
   - Create docker image:
      ```bash
      docker build -t logging .
      ```
   - Run docker:
      ```bash
      docker run -d --name logging -p 8000:8000 logging
      ```

9. Set up .env:

``` bash
# Copy the .env.sample file to .env and fill in the required values.
```
---

## Usage

1. Start the FastAPI server:
   ```bash
   uvicorn app:app --port 8020 --reload
   ```
2. Access the API documentation at:
   ```
   http://127.0.0.1:8020/docs
   # for detailed docs visit 👉 http://127.0.0.1:8020/scalar
   ```
   
3. Use the API to book, reschedule, or cancel meetings, and view past and upcoming meetings.

---

## API Endpoints

### Meeting Endpoints
- **POST /book-meeting**: Book a new meeting.
- **POST /reschedule-meeting**: Reschedule an existing meeting.
- **POST /cancel-meeting**: Cancel a meeting.
- **GET /meetings**: View all meetings (past and upcoming).

---

## Project Structure

```plaintext
meeting-scheduler/
├── .env
├── .gitignore  # gitignore file for GitHub
├── README.md  # Project documentation
├── __init__.py  # initializes package
├── app.py  # main FastAPI app
├── book_meeting
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
- Implement notifications for meeting bookings, rescheduling, and cancellations.
- Add support for recurring meetings.
- Integrate with calendar services (e.g., Google Calendar, Microsoft Outlook) for seamless meeting scheduling.

---

## Contribution Guidelines
Contributions are welcome! To contribute:
1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Commit your changes and submit a pull request.

---

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE.md) file for details.

---

## Author
**Madhur-Prakash**  
[GitHub](https://github.com/Madhur-Prakash) | [Medium](https://medium.com/@madhurprakash2005)