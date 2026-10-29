# AI-Based Smart Parking Management System

Intermediate-level educational project using Python, Flask, SQLite, and Scikit-learn.

## Features

- User registration and login with hashed passwords
- Admin and regular-user roles
- Parking-slot dashboard
- Reservation and cancellation
- Basic overlap checks for reservations
- Admin slot-status management
- ML model to estimate hourly occupied-slot counts
- Evaluation with MAE and a simple mean baseline

## 1. Requirements

- Python 3.10 or newer
- Visual Studio Code (recommended)
- Internet connection for Bootstrap CSS/JS CDN, or download Bootstrap locally

## 2. Setup (Windows)

Open a terminal in the project root:

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Train the ML model

From the project root:

```powershell
python ml/train_model.py
```

This creates `ml/parking_model.pkl`. The included `parking_data.csv` is synthetic demo data only; the measured test score is not evidence of real-world performance.

## 4. Run the web app

```powershell
python app.py
```

Open `http://127.0.0.1:5000`.

On first launch, the app creates a SQLite database and 20 demo parking slots.

### Demo administrator account

- Email: `admin@parking.local`
- Password: `Admin123!`

Change or remove this demo account before any deployment. The secret key in `app.py` is also a development placeholder and must be replaced.

## 5. Dataset format

`ml/parking_data.csv` includes:

- `timestamp`: date/time for the observation
- `hour`: hour of day, 0–23
- `day_of_week`: Monday=0 through Sunday=6
- `is_weekend`: 1 for Saturday/Sunday, otherwise 0
- `occupied_slots`: observed occupied-slot count

Use real, representative data for meaningful predictions. Keep timestamps ordered and use a time-based test split.

## 6. Important limitations

- The application does not connect to live cameras or physical sensors.
- The slot status shown in the dashboard is manually maintained by the admin.
- The current booking form only offers slots whose general status is `available`. The server checks overlapping bookings for the selected time range, but this is a learning prototype rather than a production reservation platform.
- For production, add CSRF protection, rate limiting, stronger authorization and audit logs, robust transaction/locking for concurrent bookings, time-zone handling, database migrations, secret management, and automated tests.
- Do not use the demo credentials or development secret key in a public deployment.

## Project structure

```text
smart_parking_management/
├── app.py
├── models.py
├── extensions.py
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── booking.html
│   └── admin.html
├── static/
│   ├── style.css
│   └── script.js
└── ml/
    ├── train_model.py
    ├── predict.py
    ├── parking_data.csv
    └── parking_model.pkl  # generated after training
```
