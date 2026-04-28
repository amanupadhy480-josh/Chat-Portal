from gevent import monkey
monkey.patch_all()

import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aman_portal_2026_final'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])

# Database Config
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"): 
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///chat_v4.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(200), default='default_dp.png')
    is_online = db.Column(db.Boolean, default=False)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    contact_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(1000))
    file_path = db.Column(db.String(200))
    sender = db.Column(db.String(50))
    receiver = db.Column(db.String(50))
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Core Routes ---

@app.route('/')
@login_required
def home():
    # Gets all users added as contacts
    contacts = db.session.query(User).join(Contact, Contact.contact_user_id == User.id).filter(Contact.owner_id == current_user.id).all()
    return render_template('home.html', contacts=contacts)

@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    mobile = request.form.get('mobile')
    target = User.query.filter_by(mobile=mobile).first()
    if target and target.id != current_user.id:
        exists = Contact.query.filter_by(owner_id=current_user.id, contact_user_id=target.id).first()
        if not exists:
            new_c = Contact(owner_id=current_user.id, contact_user_id=target.id)
            db.session.add(new_c)
            db.session.commit()
    return redirect(url_for('home'))

@app.route('/delete_contact/<int:id>')
@login_required
def delete_contact(id):
    c = Contact.query.filter_by(owner_id=current_user.id, contact_user_id=id).first()
    if c:
        db.session.delete(c)
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/upload_profile', methods=['POST'])
@login_required
def upload_profile():
    file = request.files.get('pic')
    if file:
        filename = secure_filename(f"user_{current_user.id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        current_user.profile_pic = filename
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/send_file', methods=['POST'])
@login_required
def send_file():
    file = request.files.get('file')
    recipient = request.form.get('recipient')
    if file:
        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)
        new_msg = Message(file_path=filename, sender=current_user.username, receiver=recipient)
        db.session.add(new_msg)
        db.session.commit()
        socketio.emit('new_msg', {'msg': 'Sent a file 📎', 'sender': current_user.username, 'recipient': recipient})
    return redirect(url_for('chat', username=recipient))

# --- Standard Auth & Socket Logic ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(mobile=request.form.get('mobile')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            user.is_online = True
            db.session.commit()
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/chat/<username>')
@login_required
def chat(username):
    target = User.query.filter_by(username=username).first()
    msgs = Message.query.filter(
        ((Message.sender == current_user.username) & (Message.receiver == username)) |
        ((Message.sender == username) & (Message.receiver == current_user.username))
    ).order_by(Message.timestamp).all()
    return render_template('chat.html', recipient=target, messages=msgs)

@socketio.on('private_message')
def handle_msg(data):
    new_msg = Message(content=data['message'], sender=current_user.username, receiver=data['recipient'])
    db.session.add(new_msg)
    db.session.commit()
    emit('new_msg', {'msg': data['message'], 'sender': current_user.username, 'recipient': data['recipient']}, broadcast=True)

@app.route('/init_db')
def init_db():
    db.drop_all()
    db.create_all()
    return "DB Reset! Go to /signup"

if __name__ == '__main__':
    socketio.run(app, debug=True)
