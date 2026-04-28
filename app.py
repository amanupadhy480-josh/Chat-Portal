from gevent import monkey
monkey.patch_all()

import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aman_portal_2026_full'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024 # 20MB limit for files

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
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

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
    file_path = db.Column(db.String(200)) # For file sharing
    sender = db.Column(db.String(50))
    receiver = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Database Init ---
@app.route('/init_db')
def init_db():
    db.create_all()
    return "Database Initialized!"

# --- Account & Contacts Management ---
@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    mobile = request.form.get('mobile')
    target_user = User.query.filter_by(mobile=mobile).first()
    if target_user:
        new_c = Contact(user_id=current_user.id, contact_username=target_user.username, contact_mobile=mobile)
        db.session.add(new_c)
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/delete_contact/<int:id>')
@login_required
def delete_contact(id):
    c = Contact.query.get(id)
    if c and c.user_id == current_user.id:
        db.session.delete(c)
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user = User.query.get(current_user.id)
    Contact.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    logout_user()
    return redirect(url_for('signup'))

# --- File Sharing Route ---
@app.route('/send_file', methods=['POST'])
@login_required
def send_file():
    if 'file' not in request.files: return "No file"
    file = request.files['file']
    recipient = request.form.get('recipient')
    if file:
        filename = secure_filename(f"file_{datetime.now().timestamp()}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        msg = Message(content=file.filename, file_path=filename, sender=current_user.username, receiver=recipient)
        db.session.add(msg)
        db.session.commit()
        return jsonify({"status": "sent", "filename": filename})

# --- Real-time Logic ---
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        current_user.is_online = True
        db.session.commit()
        emit('user_status', {'user': current_user.username, 'status': 'online'}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        current_user.is_online = False
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        emit('user_status', {'user': current_user.username, 'status': 'offline'}, broadcast=True)

@socketio.on('private_message')
def handle_private_msg(data):
    msg = Message(content=data['message'], sender=current_user.username, receiver=data['recipient'])
    db.session.add(msg)
    db.session.commit()
    emit('new_msg', {
        'msg': data['message'], 
        'sender': current_user.username, 
        'recipient': data['recipient'],
        'time': datetime.now().strftime('%I:%M %p')
    }, broadcast=True)

# Main Routes
@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    # Logic to find people who messaged you but aren't in contacts
    return render_template('home.html', contacts=contacts)

@app.route('/chat/<username>')
@login_required
def chat(username):
    target = User.query.filter_by(username=username).first()
    msgs = Message.query.filter(
        ((Message.sender == current_user.username) & (Message.receiver == username)) |
        ((Message.sender == username) & (Message.receiver == current_user.username))
    ).order_by(Message.timestamp).all()
    return render_template('chat.html', recipient=target, messages=msgs)

# Auth routes (Login/Signup/Logout/Uploads) - [Aapke pehle wale standard code jaisa]
# ... (Login, Signup implementation same as before)

if __name__ == '__main__':
    socketio.run(app, debug=True)
