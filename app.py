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
app.config['SECRET_KEY'] = 'skyline_secret_2026'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])

# Database Config
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"): uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri or "sqlite:///skyline_chat.db"
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
    file_type = db.Column(db.String(20))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# --- Routes ---
@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    clist = []
    for c in contacts:
        u = User.query.filter_by(mobile=c.c_mobile).first()
        clist.append({
            'id': c.id, 'name': c.c_name, 'mobile': c.c_mobile,
            'pic': u.profile_pic if u else 'default_dp.png',
            'online': u.is_online if u else False
        })
    return render_template('home.html', contacts=clist)

@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    m = request.form.get('mobile')
    target = User.query.filter_by(mobile=m).first()
    if target:
        # Check if already added
        exists = Contact.query.filter_by(user_id=current_user.id, c_mobile=m).first()
        if not exists:
            db.session.add(Contact(user_id=current_user.id, c_name=target.username, c_mobile=m))
            db.session.commit()
            flash("Contact added!")
        else: flash("Already in contacts.")
    else: flash("User not found on SkyLine.")
    return redirect(url_for('home'))

@app.route('/upload_profile', methods=['POST'])
@login_required
def upload_profile():
    file = request.files.get('pic')
    if file:
        filename = secure_filename(f"dp_{current_user.id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        current_user.profile_pic = filename
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/chat/<name>/<mobile>')
@login_required
def chat(name, mobile):
    # Mark as read
    Message.query.filter_by(sender=mobile, receiver=current_user.mobile).update({Message.is_read: True})
    db.session.commit()
    msgs = Message.query.filter(
        ((Message.sender == current_user.mobile) & (Message.receiver == mobile)) |
        ((Message.sender == mobile) & (Message.receiver == current_user.mobile))
    ).order_by(Message.timestamp).all()
    target_user = User.query.filter_by(mobile=mobile).first()
    return render_template('chat.html', r_name=name, r_mobile=mobile, messages=msgs, target=target_user)

@app.route('/init_db')
def init_db():
    db.drop_all()
    db.create_all()
    return "SkyLine Database Refreshed! Signup again."

# login, signup, logout routes remain same...
# [Include your existing login/signup logic here]

if __name__ == '__main__':
    socketio.run(app)
