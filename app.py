from datetime import datetime
from functools import wraps
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager, UserMixin, current_user, login_required, login_user, logout_user
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
ML_DIR = BASE_DIR / "ml"

app = Flask(__name__)
app.config["SECRET_KEY"] = "replace-this-with-a-long-random-secret-before-deployment"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR / 'smart_parking.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

from extensions import db

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


# Models are in a separate file but share this SQLAlchemy instance.
from models import User, ParkingSlot, Booking, ParkingHistory  # noqa: E402


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            flash("Administrator access is required.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def parse_datetime(value):
    """Parse an HTML datetime-local value, returning None if invalid."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def seed_data():
    """Create demo slots and a demo admin account on first launch."""
    if ParkingSlot.query.count() == 0:
        for number in range(1, 21):
            db.session.add(ParkingSlot(slot_number=f"A{number:02d}", status="available"))
    if User.query.filter_by(email="admin@parking.local").first() is None:
        admin = User(
            name="Demo Admin",
            email="admin@parking.local",
            password_hash=generate_password_hash("Admin123!"),
            role="admin",
        )
        db.session.add(admin)
    db.session.commit()


def get_prediction():
    """Return a prediction if a trained model exists; otherwise show a helpful fallback."""
    model_path = ML_DIR / "parking_model.pkl"
    if not model_path.exists():
        return {
            "available": None,
            "occupied": None,
            "demand": "Not trained",
            "message": "Train the model with: python ml/train_model.py",
        }

    try:
        model = joblib.load(model_path)
        now = datetime.now()
        features = pd.DataFrame([{
            "hour": now.hour,
            "day_of_week": now.weekday(),
            "is_weekend": int(now.weekday() >= 5),
        }])
        predicted = float(model.predict(features)[0])
        total = ParkingSlot.query.count()
        occupied = max(0, min(total, round(predicted)))
        available = max(0, total - occupied)
        occupancy_pct = (occupied / total * 100) if total else 0

        if occupancy_pct < 35:
            demand = "Low"
        elif occupancy_pct < 70:
            demand = "Medium"
        else:
            demand = "High"

        return {
            "available": available,
            "occupied": occupied,
            "demand": demand,
            "message": f"Estimated occupancy for the current hour ({now.strftime('%H:00')}).",
        }
    except Exception:
        app.logger.exception("Could not load or run the parking prediction model")
        return {
            "available": None,
            "occupied": None,
            "demand": "Unavailable",
            "message": "Prediction could not be generated. Retrain the model and try again.",
        }


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("base.html", landing=True)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please complete every field.", "danger")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
        else:
            user = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
                role="user",
            )
            db.session.add(user)
            db.session.commit()
            flash("Account created. You can now log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Welcome back!", "success")
            return redirect(url_for("admin" if user.role == "admin" else "dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    slots = ParkingSlot.query.order_by(ParkingSlot.slot_number).all()
    total = len(slots)
    available = sum(slot.status == "available" for slot in slots)
    occupied = sum(slot.status == "occupied" for slot in slots)
    reserved = sum(slot.status == "reserved" for slot in slots)
    prediction = get_prediction()
    my_bookings = (
        Booking.query.filter_by(user_id=current_user.id)
        .order_by(Booking.start_time.desc()).limit(5).all()
    )
    return render_template(
        "dashboard.html", slots=slots, total=total, available=available,
        occupied=occupied, reserved=reserved, prediction=prediction,
        my_bookings=my_bookings, now=datetime.now(),
    )


@app.route("/booking", methods=["GET", "POST"])
@login_required
def booking():
    available_slots = ParkingSlot.query.filter_by(status="available").order_by(
        ParkingSlot.slot_number
    ).all()

    if request.method == "POST":
        slot_id = request.form.get("slot_id", type=int)
        start_time = parse_datetime(request.form.get("start_time", ""))
        end_time = parse_datetime(request.form.get("end_time", ""))

        slot = db.session.get(ParkingSlot, slot_id) if slot_id else None
        if not slot:
            flash("Please select a valid parking slot.", "danger")
        elif not start_time or not end_time:
            flash("Enter valid start and end times.", "danger")
        elif start_time <= datetime.now():
            flash("The start time must be in the future.", "danger")
        elif end_time <= start_time:
            flash("The end time must be after the start time.", "danger")
        else:
            # Any active reservation that overlaps this interval blocks the slot.
            conflict = Booking.query.filter(
                Booking.slot_id == slot.id,
                Booking.status == "active",
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            ).first()

            if conflict:
                flash("That slot is already booked for part of this time range.", "danger")
            else:
                booking_record = Booking(
                    user_id=current_user.id,
                    slot_id=slot.id,
                    start_time=start_time,
                    end_time=end_time,
                    status="active",
                )
                db.session.add(booking_record)
                # Reserved status is a simple display status. Availability for future
                # time ranges is determined by booking overlap checks.
                db.session.commit()
                flash(f"Slot {slot.slot_number} booked successfully.", "success")
                return redirect(url_for("dashboard"))

    all_slots = ParkingSlot.query.order_by(ParkingSlot.slot_number).all()
    return render_template("booking.html", slots=all_slots, now=datetime.now())


@app.route("/booking/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    record = db.session.get(Booking, booking_id)
    if not record:
        flash("Booking not found.", "danger")
    elif record.user_id != current_user.id and current_user.role != "admin":
        flash("You cannot cancel another user's booking.", "danger")
    elif record.status != "active":
        flash("This booking is already inactive.", "warning")
    else:
        record.status = "cancelled"
        db.session.commit()
        flash("Booking cancelled.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    if request.method == "POST":
        slot_id = request.form.get("slot_id", type=int)
        new_status = request.form.get("status", "")
        slot = db.session.get(ParkingSlot, slot_id) if slot_id else None
        if not slot or new_status not in {"available", "occupied", "reserved"}:
            flash("Invalid slot or status.", "danger")
        else:
            slot.status = new_status
            db.session.add(ParkingHistory(
                slot_id=slot.id,
                timestamp=datetime.now(),
                occupied=(new_status == "occupied"),
            ))
            db.session.commit()
            flash(f"{slot.slot_number} updated to {new_status}.", "success")
        return redirect(url_for("admin"))

    slots = ParkingSlot.query.order_by(ParkingSlot.slot_number).all()
    bookings = Booking.query.order_by(Booking.start_time.desc()).limit(30).all()
    users_count = User.query.count()
    return render_template("admin.html", slots=slots, bookings=bookings, users_count=users_count)


@app.errorhandler(404)
def not_found(_error):
    return render_template("base.html", landing=True, not_found=True), 404


with app.app_context():
    db.create_all()
    seed_data()


if __name__ == "__main__":
    # Debug is convenient for local development; disable it for deployment.
    app.run(debug=True)
