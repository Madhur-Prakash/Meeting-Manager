# Appointment Booking System

**A FastAPI-Based Appointment Booking Application**

## Overview
This project is a simple and efficient appointment booking system implemented using FastAPI and MongoDB. It allows users to book appointments with specific doctors, ensuring a 30-minute time gap between appointments to avoid scheduling conflicts.

---

## Features
- **Doctor and Patient Management**: Manage appointments for doctors and patients with ease.
- **Time Slot Validation**: Ensures a minimum 30-minute gap between consecutive appointments for the same doctor.
- **Interactive Web Interface**: Utilizes Jinja2 templates for user-friendly appointment booking and viewing.
- **Secure and Scalable**: Built with FastAPI and MongoDB for high performance and scalability.

---

## Technology Stack
- **Backend Framework**: FastAPI
- **Database**: MongoDB
- **Frontend Templates**: Jinja2
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
5. Set up MongoDB:
   - Install MongoDB and start the service.
   - Configure the MongoDB URI in the `.env` file.

---

## Usage

1. Start the FastAPI server:
   ```bash
   uvicorn app:app --reload
   ```
2. Access the web interface at:
   ```
   http://127.0.0.1:8000/
   ```
3. Use the interface to:
   - View existing appointments.
   - Book a new appointment by providing details such as doctor name, patient name, email, and desired time slot.

---

## API Endpoints

### Appointment Management
- **GET /**: Retrieve and display all appointments.
- **POST /**: Book a new appointment with time slot validation.

---

## Project Structure

```plaintext
appointment-booking/
├── booking/
│   ├── templates/       # HTML templates (Jinja2)
│   ├── __init__.py      # Package initializer
│   ├── book.py          # API routes for booking
│   ├── databse.py       # MongoDB connection setup
│   ├── models.py        # Database models
│   ├── schemas.py       # Data schemas for validation
├── app.py               # Entry point for FastAPI
├── requirements.txt     # Python dependencies
├── .gitignore           # Ignored files and directories
├── README.md            # Project documentation
```

---

## Future Enhancements
- Add user authentication for patients and doctors.
- Implement notification system for appointment reminders.
- Provide a dashboard for managing appointments and doctor availability.

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
**Madhur Prakash**  
[GitHub](https://github.com/Madhur-Prakash) | [Medium](https://medium.com/@madhurprakash2005)

---

## Acknowledgements
- Faculty Guide: Anshul Tickoo
- Amity School of Engineering and Technology
