from gevent import monkey
monkey.patch_all()

import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aman_portal_2026'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])

# Database Setup
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"): 
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///aman_chat.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
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
    file_path = db.Column(db.String(200))
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
    contact_list = []
    for c in contacts:
        u = User.query.filter_by(mobile=c.contact_mobile).first()
        status = u.is_online if u else False
        pic = u.profile_pic if u else 'default_dp.png'
        contact_list.append({'name': c.contact_name, 'mobile': c.contact_mobile, 'online': status, 'pic': pic})
    return render_template('home.html', contacts=contact_list)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('username')
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        
        if not User.query.filter_by(mobile=mobile).first():
            hashed_pw = generate_password_hash(password)
            new_user = User(username=name, mobile=mobile, password=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        else:
            flash("Mobile number already registered!")
    return render_template('signup.html') # Aapki signup.html file yahan load hogi

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        user = User.query.filter_by(mobile=mobile).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            user.is_online = True
            db.session.commit()
            return redirect(url_for('home'))
        else:
            flash("Invalid credentials!")
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
    new_msg = Message(content=data['message'], sender=data['sender'], receiver=data['recipient'])
    db.session.add(new_msg)
    db.session.commit()
    emit('new_msg', data, broadcast=True)

@app.route('/init_db')
def init_db():
    db.drop_all() # Purani tables delete karne ke liye
    db.create_all() # Nayi tables banane ke liye
    return "Database Refreshed Successfully!"

if __name__ == '__main__':
    socketio.run(app, debug=True)
