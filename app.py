from gevent import monkey
monkey.patch_all()

import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aman_portal_2026'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])

# Database Configuration
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"): 
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///aman_chat.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(200), default='default_dp.png')
    is_online = db.Column(db.Boolean, default=False)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    contact_name = db.Column(db.String(50))
    contact_mobile = db.Column(db.String(15))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(1000))
    sender = db.Column(db.String(50))
    receiver = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---
@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    return render_template('home.html', contacts=contacts)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u = request.form.get('username')
        m = request.form.get('mobile')
        p = request.form.get('password')
        if not User.query.filter_by(mobile=m).first():
            new_u = User(username=u, mobile=m, password=generate_password_hash(p))
            db.session.add(new_u)
            db.session.commit()
            return redirect(url_for('login'))
        flash("Mobile already exists!")
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        m = request.form.get('mobile')
        p = request.form.get('password')
        user = User.query.filter_by(mobile=m).first()
        if user and check_password_hash(user.password, p):
            login_user(user)
            user.is_online = True
            db.session.commit()
            return redirect(url_for('home'))
        flash("Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    current_user.is_online = False
    db.session.commit()
    logout_user()
    return redirect(url_for('login'))

@app.route('/chat/<name>/<mobile>')
@login_required
def chat(name, mobile):
    msgs = Message.query.filter(
        ((Message.sender == current_user.mobile) & (Message.receiver == mobile)) |
        ((Message.sender == mobile) & (Message.receiver == current_user.mobile))
    ).order_by(Message.timestamp).all()
    return render_template('chat.html', r_name=name, r_mobile=mobile, messages=msgs)

@socketio.on('private_message')
def handle_msg(data):
    msg = Message(content=data['message'], sender=data['sender'], receiver=data['recipient'])
    db.session.add(msg)
    db.session.commit()
    emit('new_msg', data, broadcast=True)

@app.route('/init_db')
def init_db():
    db.create_all()
    return "Database Created!"

if __name__ == '__main__':
    socketio.run(app)
            
