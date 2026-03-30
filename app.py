from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///memoryquest.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    start_location = db.Column(db.String(200))
    max_hours_per_day = db.Column(db.Float, default=8)
    travel_style = db.Column(db.String(50))  # relaxed, moderate,packed
    is_public = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Destination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200))
    order = db.Column(db.Integer)
    day_number = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SharedTrip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    shared_with_email = db.Column(db.String(120))
    can_edit = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    trips = Trip.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', trips=trips)

@app.route('/api/trips', methods=['GET', 'POST'])
@login_required
def trips_api():
    if request.method == 'POST':
        data = request.json
        trip = Trip(
            user_id=current_user.id,
            name=data.get('name'),
            start_location=data.get('start_location'),
            max_hours_per_day=data.get('max_hours_per_day', 8),
            travel_style=data.get('travel_style', 'moderate')
        )
        db.session.add(trip)
        db.session.commit()
        return jsonify({'id': trip.id, 'name': trip.name})
    
    trips = Trip.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'start_location': t.start_location,
        'max_hours_per_day': t.max_hours_per_day,
        'travel_style': t.travel_style
    } for t in trips])

@app.route('/api/trips/<int:trip_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def trip_detail(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'DELETE':
        db.session.delete(trip)
        db.session.commit()
        return jsonify({'success': True})
    
    if request.method == 'PUT':
        data = request.json
        trip.name = data.get('name', trip.name)
        trip.start_location = data.get('start_location', trip.start_location)
        trip.max_hours_per_day = data.get('max_hours_per_day', trip.max_hours_per_day)
        trip.travel_style = data.get('travel_style', trip.travel_style)
        db.session.commit()
        return jsonify({'success': True})
    
    destinations = Destination.query.filter_by(trip_id=trip_id).order_by(Destination.order).all()
    return jsonify({
        'id': trip.id,
        'name': trip.name,
        'start_location': trip.start_location,
        'max_hours_per_day': trip.max_hours_per_day,
        'travel_style': trip.travel_style,
        'destinations': [{
            'id': d.id,
            'name': d.name,
            'location': d.location,
            'order': d.order,
            'day_number': d.day_number,
            'notes': d.notes
        } for d in destinations]
    })

@app.route('/api/trips/<int:trip_id>/destinations', methods=['POST'])
@login_required
def add_destination(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    dest = Destination(
        trip_id=trip_id,
        name=data.get('name'),
        location=data.get('location'),
        order=data.get('order', 0),
        day_number=data.get('day_number'),
        notes=data.get('notes')
    )
    db.session.add(dest)
    db.session.commit()
    return jsonify({'id': dest.id, 'name': dest.name})

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already exists')
        
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            name=name
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        
        return render_template('login.html', error='Invalid email or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/trip/<int:trip_id>')
@login_required
def trip_view(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if trip.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    return render_template('trip.html', trip=trip)

# Create tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)