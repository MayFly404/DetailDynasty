import os
from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory, send_file, jsonify
from werkzeug.utils import secure_filename
from replit import db
from flask_sqlalchemy import SQLAlchemy

import secrets
import re
import mimetypes
import sqlite3
import json
import time

from flask_ckeditor import CKEditor
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
ckeditor = CKEditor(app)

app.secret_key = os.environ['SECRET_KEY']
app.config[
 'SQLALCHEMY_DATABASE_URI'] = 'sqlite:///car_detailing.db'  # SQLite database
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

import paypalrestsdk
import stripe

# Initialize the PayPal SDK with the sandbox credentials
paypalrestsdk.configure({
    "mode": "sandbox",  # Change to "live" for production
    "client_id": "YOUR_PAYPAL_CLIENT_ID",
    "client_secret": "YOUR_PAYPAL_CLIENT_SECRET"
})

# Set your Stripe API keys
stripe.api_key = os.environ['STRIPE_API']


# Database models
class Booking(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	first_name = db.Column(db.String(50), nullable=False)
	last_name = db.Column(db.String(50), nullable=False)
	address = db.Column(db.String(200), nullable=False)
	date = db.Column(db.Date, nullable=False)
	time = db.Column(db.String(5), nullable=False)
	booked_by = db.Column(db.String(100), nullable=False)


# Database models for user credentials
class User(db.Model, UserMixin):
	id = db.Column(db.Integer, primary_key=True)
	username = db.Column(db.String(100), unique=True, nullable=False)
	password = db.Column(db.String(100), nullable=False)
	role = db.Column(db.String(50),
	                 default='user')  # New field for user role, default is 'user'
	is_admin = db.Column(
	 db.Boolean, default=False)  # New field for admin access, default is False

	def get_id(self):
		return str(self.id)


@app.route('/')
def index():
	return render_template('home.html')


@app.route('/services')
def services():
	return render_template('services.html')


@app.route('/about')
def about():
	return render_template('about.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
	if request.method == 'POST':
		username = request.form['username']
		password = request.form['password']

		# Check if the username already exists in the database
		existing_user = User.query.filter_by(username=username).first()
		if existing_user:
			error_message = 'Username already exists. Please choose a different username.'
			return render_template('signup.html', error_message=error_message)

		# Create a new user and store the credentials in the database
		new_user = User(username=username, password=password)
		db.session.add(new_user)
		db.session.commit()

		session['username'] = username
		return redirect(url_for('login'))

	return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		username = request.form['username']
		password = request.form['password']

		# Retrieve the user's data from the database
		user = User.query.filter_by(username=username).first()

		if user and user.password == password:
			login_user(user)  # This will set the current_user variable
			return redirect(url_for('book'))
		else:
			error_message = 'Invalid credentials. Please try again.'
			return render_template('login.html', error_message=error_message)

	return render_template('login.html')


@login_manager.user_loader
def load_user(user_id):
	return User.query.get(int(user_id))


@app.route('/logout')
def logout():
	# Clear session data (user logout)
	session.clear()

	# Redirect to the home page after logout
	return redirect(url_for('index'))

@app.route('/book', methods=['GET', 'POST'])
def book():
    if not current_user:
        return "You don't have access."

    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        address = request.form['address']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        time = request.form['time']
        selected_service = request.form.get('service')
        total_amount = 0

        service_prices = {
            'service1': 35,
            'service2': 45,
            'service3': 70,
            'service4': 110,
            'service5': 135,
            # Add more services and their corresponding prices as needed
        }

        # Get the price for the selected service
        total_amount = service_prices.get(selected_service)

        # Check if the chosen date and time are already booked
        existing_booking = Booking.query.filter_by(date=date, time=time).first()
        if existing_booking:
            error_message = 'The selected date and time are already booked. Please choose a different time.'
            return render_template('book.html', error_message=error_message)

        # Create a new booking with the logged-in user's username
        new_booking = Booking(first_name=first_name,
                              last_name=last_name,
                              address=address,
                              date=date,
                              time=time,
                              booked_by=current_user.username)
        db.session.add(new_booking)
        db.session.commit()

        # Payment processing
        payment_method = request.form.get('payment_method')

        if payment_method == 'card':
            # Process the payment using Stripe
            try:
                charge = stripe.Charge.create(
                    amount=int(total_amount * 100),  # Stripe requires amount in cents
                    currency="USD",
                    description="Car Detailing Service",
                    source=request.form['card_number'],  # User's credit card number obtained from the form
                )
                # Payment success
                # ... (Additional logic for successful payment)

            except stripe.error.CardError as e:
                # Handle payment failure due to card issues
                return "Payment failed. Please check your card details and try again."
            except Exception as e:
                # Handle other payment errors
                return "Payment error. Please try again later."

        elif payment_method == 'on_site':
            # No online payment required for pay on site option
            # You can add any additional logic related to pay on site here
            pass

        else:
            # Handle invalid payment method selection
            return "Invalid payment method. Please choose a valid payment method."

        return redirect(url_for('booking_confirmation'))

    return render_template('book.html')


# Booking Confirmation Page
@app.route('/booking_confirmation')
def booking_confirmation():
	return render_template('booking_confirmation.html')


# Admin Panel
@app.route('/admin')
@login_required
def admin():
	if not current_user.is_admin:
		return "You don't have admin access."

	bookings = Booking.query.all()
	users = User.query.all()
	return render_template('admin.html', bookings=bookings, users=users)


# Endpoint to show booking details
@app.route('/booking_details/<int:booking_id>')
@login_required
def booking_details(booking_id):
	if not current_user.is_admin:
		return "You don't have admin access."

	booking = Booking.query.get_or_404(booking_id)
	return render_template('booking_details.html', booking=booking)

@app.route('/promote_to_admin/<int:user_id>', methods=['POST'])
@login_required
def promote_to_admin(user_id):
    if not current_user.is_admin:
        return "You don't have admin access."

    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()
    return jsonify({'message': 'User promoted to admin successfully.'})

    # After promoting the user, redirect the admin to the admin panel
    return redirect(url_for('admin'))


@app.route('/demote_admin/<int:user_id>', methods=['POST'])
@login_required
def demote_admin(user_id):
    if not current_user.is_admin:
        return "You don't have admin access."

    user = User.query.get_or_404(user_id)
    user.is_admin = False
    db.session.commit()
    return jsonify({'message': 'Admin demoted successfully.'})

    # After demoting the admin, redirect the admin to the admin panel
    return redirect(url_for('admin'))



@app.route('/remove_booking/<int:booking_id>', methods=['POST'])
@login_required
def remove_booking(booking_id):
	if not current_user.is_admin:
		return "You don't have admin access."
	
	booking = Booking.query.get_or_404(booking_id)
	db.session.delete(booking)
	db.session.commit()
	return jsonify({'message': 'Booking removed successfully.'})
	
	returnToAdmin()



def returnToAdmin():
	time.sleep(1)
	return redirect(url_for('admin'))


@login_manager.user_loader
def load_user(user_id):
	return User.query.get(int(user_id))

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='img/favicon.ico')

if __name__ == '__main__':
	with app.app_context():
		# Initialize the database and create the required tables
		db.create_all()

	app.run(host='0.0.0.0', port=8080)
