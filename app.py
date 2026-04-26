import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'aman_portal_2026')

uri = os.getenv("DATABASE_URL", "sqlite:///chat.db")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

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

@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    saved_mobiles = [c.contact_mobile for c in contacts]
    
    # Unknown messengers logic
    unknown_msgs = Message.query.filter_by(receiver=current_user.username).all()
    unknown_users = []
    seen_mobiles = set()
    for m in unknown_msgs:
        u_info = User.query.filter_by(username=m.sender).first()
        if u_info and u_info.mobile not in saved_mobiles and u_info.mobile not in seen_mobiles:
            unknown_users.append({'username': u_info.username, 'mobile': u_info.mobile})
            seen_mobiles.add(u_info.mobile)

    return render_template('home.html', contacts=contacts, unknown=unknown_users)

@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    mobile = request.form.get('mobile')
    user_to_add = User.query.filter_by(mobile=mobile).first()
    if user_to_add:
        if user_to_add.id == current_user.id:
            flash("You can't add yourself!")
        else:
            exists = Contact.query.filter_by(user_id=current_user.id, contact_mobile=mobile).first()
            if not exists:
                new_c = Contact(user_id=current_user.id, contact_username=user_to_add.username, contact_mobile=mobile)
                db.session.add(new_c)
                db.session.commit()
    return redirect(url_for('home'))

@app.route('/reject_unknown/<username>')
@login_required
def reject_unknown(username):
    Message.query.filter_by(sender=username, receiver=current_user.username).delete()
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
    Message.query.filter((Message.sender == user.username) | (Message.receiver == user.username)).delete()
    db.session.delete(user)
    db.session.commit()
    logout_user()
    return redirect(url_for('signup'))

@app.route('/chat/<recipient>')
@login_required
def chat(recipient):
    target_user = User.query.filter_by(username=recipient).first()
    messages = Message.query.filter(
        ((Message.sender == current_user.username) & (Message.receiver == recipient)) |
        ((Message.sender == recipient) & (Message.receiver == current_user.username))
    ).order_by(Message.timestamp.asc()).all()
    return render_template('index.html', recipient=recipient, recipient_mobile=target_user.mobile if target_user else "", saved_messages=messages)

# Login, Signup, Logout routes (Keep them as they are in your source)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        user = User.query.filter_by(mobile=mobile).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('home'))
        flash('Invalid Credentials')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        mobile = request.form.get('mobile').strip()
        password = request.form.get('password')
        if User.query.filter_by(mobile=mobile).first() or User.query.filter_by(username=username).first():
            flash('User already exists!')
            return redirect(url_for('signup'))
        new_user = User(username=username, mobile=mobile, password=generate_password_hash(password, method='pbkdf2:sha256'))
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
    new_msg = Message(content=data['message'], sender=current_user.username, receiver=data['recipient'])
    db.session.add(new_msg)
    db.session.commit()
    emit('new_msg', {
        'msg': data['message'], 
        'sender': current_user.username, 
        'recipient': data['recipient']
    }, broadcast=True)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
    
