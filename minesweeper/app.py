from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'ms_secret_2024_xK9pL'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///minesweeper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    games = db.relationship('Game', backref='player', lazy=True)


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    rows = db.Column(db.Integer, nullable=False)
    cols = db.Column(db.Integer, nullable=False)
    mines = db.Column(db.Integer, nullable=False)
    result = db.Column(db.String(10), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    played_at = db.Column(db.DateTime, default=datetime.utcnow)


def init_db():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('game'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            return render_template('register.html', error='Заполните все поля')
        if len(username) < 3:
            return render_template('register.html', error='Имя пользователя — минимум 3 символа')
        if len(password) < 4:
            return render_template('register.html', error='Пароль — минимум 4 символа')
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='Пользователь уже существует')
        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        session['username'] = user.username
        session['is_admin'] = user.is_admin
        return redirect(url_for('game'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            return redirect(url_for('game'))
        return render_template('login.html', error='Неверный логин или пароль')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/game')
def game():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('game.html', username=session['username'], is_admin=session.get('is_admin', False))


@app.route('/api/save_game', methods=['POST'])
def save_game():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400
    game = Game(
        user_id=session['user_id'],
        difficulty=data.get('difficulty', 'custom'),
        rows=int(data.get('rows', 9)),
        cols=int(data.get('cols', 9)),
        mines=int(data.get('mines', 10)),
        result=data.get('result', 'loss'),
        duration=int(data.get('duration', 0))
    )
    db.session.add(game)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    games = Game.query.filter_by(user_id=session['user_id']).order_by(Game.played_at.desc()).all()
    wins = sum(1 for g in games if g.result == 'win')
    losses = len(games) - wins
    return render_template('history.html', games=games, wins=wins, losses=losses,
                           username=session['username'])


@app.route('/admin')
def admin():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('index'))
    users = User.query.filter(User.is_admin == False).all()
    all_games = (
        db.session.query(Game, User.username)
        .join(User, Game.user_id == User.id)
        .order_by(Game.played_at.desc())
        .all()
    )
    selected_user = request.args.get('user_id', type=int)
    if selected_user:
        all_games = [(g, u) for g, u in all_games if g.user_id == selected_user]
    total_games = len(all_games)
    total_wins = sum(1 for g, _ in all_games if g.result == 'win')
    return render_template('admin.html', games=all_games, users=users,
                           selected_user=selected_user, total_games=total_games,
                           total_wins=total_wins)


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
