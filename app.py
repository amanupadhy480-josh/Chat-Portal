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
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 # 2MB Limit

# Database setup
uri = os.getenv("DATABASE_URL", "sqlite:///chat.db")
if uri.startswith("postgres://"): uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

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
def load_user(user_id): return User.query.get(int(user_id))

# Routes
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
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    user = User.query.get(current_user.id)
    user.profile_pic = filename
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/')
@login_required
def home():
    contacts = Contact.query.filter_by(user_id=current_user.id).all()
    # Adding DP info to contacts
    contact_list = []
    for c in contacts:
        u = User.query.filter_by(mobile=c.contact_mobile).first()
        contact_list.append({'id': c.id, 'username': c.contact_username, 'mobile': c.contact_mobile, 'dp': u.profile_pic if u else 'default_dp.png'})
    
    unknown_msgs = Message.query.filter_by(receiver=current_user.username).all()
    unknown_users = []
    seen = set([c.contact_mobile for c in contacts])
    for m in unknown_msgs:
        u = User.query.filter_by(username=m.sender).first()
        if u and u.mobile not in seen:
            unknown_users.append({'username': u.username, 'mobile': u.mobile, 'dp': u.profile_pic})
            seen.add(u.mobile)
            
    return render_template('home.html', contacts=contact_list, unknown=unknown_users)

@app.route('/chat/<recipient>')
@login_required
def chat(recipient):
    target_user = User.query.filter_by(username=recipient).first()
    messages = Message.query.filter(
        ((Message.sender == current_user.username) & (Message.receiver == recipient)) |
        ((Message.sender == recipient) & (Message.receiver == current_user.username))
    ).order_by(Message.timestamp.asc()).all()
    return render_template('index.html', recipient=recipient, recipient_mobile=target_user.mobile, recipient_dp=target_user.profile_pic, saved_messages=messages)

# Reuse existing routes for login, signup, logout, add_contact, delete_contact/account...
@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    mobile = request.form.get('mobile')
    user_to_add = User.query.filter_by(mobile=mobile).first()
    if user_to_add and user_to_add.id != current_user.id:
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
    emit('new_msg', {'msg': data['message'], 'sender': current_user.username, 'recipient': data['recipient']}, broadcast=True)

if __name__ == '__main__':
    if not os.path.exists('uploads'): os.makedirs('uploads')
    with app.app_context(): db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    
