         from gevent import monkey
monkey.patch_all()

import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aman_portal_ultra_2026'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Database Config
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"): uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///aman_ultra.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    mobile = db.Column(db.String(15), unique=True)
    password = db.Column(db.String(200))
    profile_pic = db.Column(db.String(200), default='default_dp.png')
    is_online = db.Column(db.Boolean, default=False)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    c_name = db.Column(db.String(50))
    c_mobile = db.Column(db.String(15))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50))
    receiver = db.Column(db.String(50))
    content = db.Column(db.String(1000))
    file_url = db.Column(db.String(200))
    file_type = db.Column(db.String(20)) # 'image' or 'video'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# --- Routes ---
@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    return render_template('home.html', contacts=contacts)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u, m, p = request.form.get('username'), request.form.get('mobile'), request.form.get('password')
        if not User.query.filter_by(mobile=m).first():
            db.session.add(User(username=u, mobile=m, password=generate_password_hash(p)))
            db.session.commit()
            return redirect(url_for('login'))
        flash("Number already registered!")
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        m, p = request.form.get('mobile'), request.form.get('password')
        user = User.query.filter_by(mobile=m).first()
        if user and check_password_hash(user.password, p):
            login_user(user)
            user.is_online = True
            db.session.commit()
            return redirect(url_for('home'))
        flash("Galti hai boss!")
    return render_template('login.html')

@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    m = request.form.get('mobile')
    target = User.query.filter_by(mobile=m).first()
    if target:
        db.session.add(Contact(user_id=current_user.id, c_name=target.username, c_mobile=m))
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

@app.route('/chat/<name>/<mobile>')
@login_required
def chat(name, mobile):
    # Mark messages as read when opening chat
    unread = Message.query.filter_by(sender=mobile, receiver=current_user.mobile, is_read=False).all()
    for m in unread: m.is_read = True
    db.session.commit()
    
    msgs = Message.query.filter(
        ((Message.sender == current_user.mobile) & (Message.receiver == mobile)) |
        ((Message.sender == mobile) & (Message.receiver == current_user.mobile))
    ).order_by(Message.timestamp).all()
    
    target_user = User.query.filter_by(mobile=mobile).first()
    return render_template('chat.html', r_name=name, r_mobile=mobile, messages=msgs, target=target_user)

@app.route('/upload_file', methods=['POST'])
@login_required
def upload_file():
    file = request.files.get('file')
    r_mobile = request.form.get('r_mobile')
    if file:
        filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        f_type = 'image' if filename.lower().endswith(('.png', '.jpg', '.jpeg')) else 'video'
        
        new_msg = Message(sender=current_user.mobile, receiver=r_mobile, file_url=filename, file_type=f_type)
        db.session.add(new_msg)
        db.session.commit()
        
        socketio.emit('new_msg', {
            'sender': current_user.mobile, 'recipient': r_mobile, 
            'file_url': filename, 'file_type': f_type
        })
    return redirect(url_for('chat', name="User", mobile=r_mobile))

@socketio.on('private_message')
def handle_msg(data):
    msg = Message(content=data['message'], sender=data['sender'], receiver=data['recipient'])
    db.session.add(msg)
    db.session.commit()
    emit('new_msg', data, broadcast=True)

@app.route('/init_db')
def init_db():
    db.create_all()
    return "Portal Ready!"

if __name__ == '__main__':
    socketio.run(app, debug=True)

