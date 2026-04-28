from gevent import monkey
monkey.patch_all()

import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aman_portal_2026_full'
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists('uploads'): os.makedirs('uploads')

# DB Config
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"): uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///chat_v3.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    mobile = db.Column(db.String(15), unique=True)
    password = db.Column(db.String(200))
    profile_pic = db.Column(db.String(200), default='default_dp.png')
    is_online = db.Column(db.Boolean, default=False)

class Contact(db.Model):
    __tablename__ = 'contacts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    contact_username = db.Column(db.String(50))
    contact_mobile = db.Column(db.String(15))

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(1000))
    file_path = db.Column(db.String(200))
    sender = db.Column(db.String(50))
    receiver = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---
@app.route('/init_db')
def init_db():
    db.create_all()
    return "Database Initialized!"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(mobile=request.form.get('mobile')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('home'))
        flash("Invalid Credentials")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        pw = generate_password_hash(request.form.get('password'))
        new_u = User(username=request.form.get('username'), mobile=request.form.get('mobile'), password=pw)
        db.session.add(new_u)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    return render_template('home.html', contacts=contacts)

@app.route('/chat/<username>')
@login_required
def chat(username):
    target = User.query.filter_by(username=username).first()
    msgs = Message.query.filter(
        ((Message.sender == current_user.username) & (Message.receiver == username)) |
        ((Message.sender == username) & (Message.receiver == current_user.username))
    ).all()
    return render_template('chat.html', recipient=target, messages=msgs)

@app.route('/uploads/<filename>')
def custom_static(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# (Add other routes like add_contact, send_file etc. from previous code)

if __name__ == '__main__':
    socketio.run(app, debug=True)
