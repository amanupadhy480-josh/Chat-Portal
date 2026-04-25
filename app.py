import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Render par secret key set karne ke liye
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'aman_portal_998877')
# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///chat.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# Render ke liye eventlet best hai
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

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
@app.route('/')
@login_required
def home():
    users = User.query.filter(User.username != current_user.username).all()
    return render_template('home.html', users=users)

@app.route('/chat/<recipient>')
@login_required
def chat(recipient):
    messages = Message.query.filter(
        ((Message.sender == current_user.username) & (Message.receiver == recipient)) |
        ((Message.sender == recipient) & (Message.receiver == current_user.username))
    ).order_by(Message.timestamp.asc()).all()
    return render_template('index.html', recipient=recipient, saved_messages=messages)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        user = User.query.filter_by(mobile=mobile).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('home'))
        flash('Invalid Mobile or Password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        
        if User.query.filter_by(mobile=mobile).first():
            flash('Number already registered!')
            return redirect(url_for('signup'))

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, mobile=mobile, password=hashed_pw)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        except:
            db.session.rollback()
            flash('System error, try again.')
            
    return render_template('signup.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@socketio.on('private_message')
def handle_msg(data):
    # Live message save karein
    new_msg = Message(content=data['message'], sender=current_user.username, receiver=data['recipient'])
    db.session.add(new_msg)
    db.session.commit()
    time_now = datetime.now().strftime("%H:%M")
    emit('new_msg', {'msg': data['message'], 'sender': current_user.username, 'time': time_now}, broadcast=True)

# Database create karein agar nahi hai toh
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # Render compatibility
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
                              
