from gevent import monkey
monkey.patch_all()

import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aman_portal_2026_full'
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists('uploads'): os.makedirs('uploads')

# Database Connection
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"): 
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///chat_v3.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# Render ke liye 'gevent' async mode zaroori hai
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

login_manager = LoginManager(app)
login_manager.login_view = 'login' # Iska naam route function ke naam se match hona chahiye

# --- Models ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
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
    sender = db.Column(db.String(50))
    receiver = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---

@app.route('/init_db')
def init_db():
    # Pehle purani table delete hogi phir nayi banegi (is_online column ke saath)
    db.drop_all() 
    db.create_all()
    return "Database structure updated successfully! Now go to /signup"

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form.get('password'))
        new_user = User(
            username=request.form.get('username'),
            mobile=request.form.get('mobile'),
            password=hashed_pw
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Account created! Please login.")
            return redirect(url_for('login'))
        except:
            db.session.rollback()
            flash("User already exists or error occurred.")
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(mobile=request.form.get('mobile')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            user.is_online = True
            db.session.commit()
            return redirect(url_for('home'))
        flash("Invalid mobile or password")
    return render_template('login.html')

@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    return render_template('home.html', contacts=contacts)

@app.route('/chat/<username>')
@login_required
def chat(username):
    target = User.query.filter_by(username=username).first()
    if not target:
        flash("User not found")
        return redirect(url_for('home'))
    
    msgs = Message.query.filter(
        ((Message.sender == current_user.username) & (Message.receiver == username)) |
        ((Message.sender == username) & (Message.receiver == current_user.username))
    ).order_by(Message.timestamp).all()
    
    return render_template('chat.html', recipient=target, messages=msgs)

@app.route('/logout')
@login_required
def logout():
    current_user.is_online = False
    db.session.commit()
    logout_user()
    return redirect(url_for('login'))

# --- Socket Events ---
@socketio.on('private_message')
def handle_msg(data):
    msg_content = data['message']
    recipient_name = data['recipient']
    
    new_msg = Message(
        content=msg_content,
        sender=current_user.username,
        receiver=recipient_name
    )
    db.session.add(new_msg)
    db.session.commit()
    
    emit('new_msg', {
        'msg': msg_content,
        'sender': current_user.username,
        'recipient': recipient_name
    }, broadcast=True) # Production mein room-based emit use karna behtar hai

if __name__ == '__main__':
    socketio.run(app, debug=True)
