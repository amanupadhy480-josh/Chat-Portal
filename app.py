# Eventlet hata kar gevent use karein, ye zyada stable hai
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
app.config['SECRET_KEY'] = 'aman_portal_2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 

# Database Configuration
uri = os.getenv("DATABASE_URL", "sqlite:///chat_v2.db")
if uri.startswith("postgres://"): 
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Threading fix for SQLite on Render
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {"check_same_thread": False} if uri.startswith("sqlite") else {},
    "pool_pre_ping": True
}

db = SQLAlchemy(app)
# Gevent mode enable kiya gaya hai
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(200), default='default_dp.png')

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contact_username = db.Column(db.String(50), nullable=False)
    contact_mobile = db.Column(db.String(15), nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    sender = db.Column(db.String(50), nullable=False)
    receiver = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/update_dp', methods=['POST'])
@login_required
def update_dp():
    if 'file' not in request.files: return redirect(url_for('home'))
    file = request.files['file']
    if file.filename == '': return redirect(url_for('home'))
    
    filename = secure_filename(f"{current_user.id}_{file.filename}")
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    user = User.query.get(current_user.id)
    user.profile_pic = filename
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    contact_list = []
    for c in contacts:
        u = User.query.filter_by(mobile=c.contact_mobile).first()
        contact_list.append({
            'id': c.id, 
            'username': c.contact_username, 
            'mobile': c.contact_mobile, 
            'dp': u.profile_pic if u else 'default_dp.png'
        })
    return render_template('home.html', contacts=contact_list, unknown=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(mobile=request.form.get('mobile')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user, remember=True)
            return redirect(url_for('home'))
        flash('Invalid mobile or password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256')
        new_user = User(username=request.form.get('username'), mobile=request.form.get('mobile'), password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@socketio.on('private_message')
def handle_msg(data):
    msg = Message(content=data['message'], sender=current_user.username, receiver=data['recipient'])
    db.session.add(msg)
    db.session.commit()
    emit('new_msg', {'msg': data['message'], 'sender': current_user.username, 'recipient': data['recipient']}, broadcast=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)
