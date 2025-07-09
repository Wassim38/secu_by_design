import os
import hvac
import pyotp
import qrcode
import io
import base64
import random
import string
import secrets  # NOUVEL IMPORT : Pour générer des jetons cryptographiquement sûrs
import time     # NOUVEL IMPORT : Pour l'horodatage
from functools import wraps # NOUVEL IMPORT : Pour créer des décorateurs propres
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageDraw, ImageFont
import mysql.connector
from dotenv import load_dotenv

# --- Initialisation et Configuration ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default-secret-key-change-me')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Connexion à Vault et à la DB (inchangé) ---
def get_vault_credentials():
    vault_addr = os.environ.get('VAULT_ADDR')
    vault_token = os.environ.get('VAULT_TOKEN')
    if not vault_addr or not vault_token:
        raise ValueError("VAULT_ADDR ou VAULT_TOKEN n'est pas défini")
    client = hvac.Client(url=vault_addr, token=vault_token)
    if not client.is_authenticated():
        raise ValueError("L'authentification à Vault a échoué")
    secret = client.secrets.kv.v2.read_secret_version(path='testvault')['data']['data']
    return secret['db_user'], secret['db_password']

def get_db_connection():
    try:
        db_user, db_password = get_vault_credentials()
        conn = mysql.connector.connect(
            host=os.environ.get('DB_HOST'),
            port=int(os.environ.get('DB_PORT')),
            user=db_user,
            password=db_password,
            database=os.environ.get('DB_NAME')
        )
        return conn
    except Exception as e:
        print(f"Erreur de connexion BDD: {e}")
        return None

# --- Modèle Utilisateur pour Flask-Login (inchangé) ---
class User(UserMixin):
    def __init__(self, id, username, otp_secret):
        self.id = id
        self.username = username
        self.otp_secret = otp_secret

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, otp_secret FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_data:
        return User(id=user_data[0], username=user_data[1], otp_secret=user_data[2])
    return None

# --- Section CAPTCHA (inchangé) ---
def generate_captcha_text(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.route('/captcha.png')
def captcha_image():
    # ... (code du captcha inchangé) ...
    captcha_text = generate_captcha_text()
    session['captcha_text'] = captcha_text
    image = Image.new('RGB', (150, 50), color='white')
    try:
        font = ImageFont.truetype("arial.ttf", 35)
    except IOError:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), captcha_text, font=font, fill='black')
    for _ in range(1500):
        draw.point((random.randint(0, 150), random.randint(0, 50)), fill='grey')
    img_io = io.BytesIO()
    image.save(img_io, 'PNG')
    img_io.seek(0)
    return Response(img_io.getvalue(), mimetype='image/png')


# --- NOUVEAU DÉCORATEUR ANTI-REJEU ---
def anti_replay_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_nonce = request.form.get('nonce')
        client_timestamp_str = request.form.get('timestamp')

        if not client_nonce or not client_timestamp_str:
            flash("Requête invalide ou corrompue.", "error")
            return redirect(request.url)

        try:
            client_timestamp = int(client_timestamp_str)
            request_age = int(time.time()) - client_timestamp
            if request_age > 300: # 5 minutes
                flash("Le formulaire a expiré. Veuillez réessayer.", "error")
                # On doit regénérer un nonce avant de rediriger
                session['nonce'] = secrets.token_hex(16)
                session['timestamp'] = int(time.time())
                return redirect(request.url)
        except (ValueError, TypeError):
            flash("Horodatage de la requête invalide.", "error")
            return redirect(request.url)

        if 'nonce' not in session or client_nonce != session.get('nonce'):
            flash("Tentative de rejeu détectée ou session invalide.", "error")
            return redirect(request.url)

        session.pop('nonce', None)
        session.pop('timestamp', None)
        return f(*args, **kwargs)
    return decorated_function


# --- ROUTES D'AUTHENTIFICATION MISES À JOUR ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Appeler le décorateur sur la logique POST
        return process_registration()

    # Logique GET : générer et envoyer le nonce au template
    nonce = secrets.token_hex(16)
    timestamp = int(time.time())
    session['nonce'] = nonce
    session['timestamp'] = timestamp
    return render_template('register.html', nonce=nonce, timestamp=timestamp)

@anti_replay_required
def process_registration():
    username = request.form.get('username')
    password = request.form.get('password')
    conn = get_db_connection()
    if not conn:
        flash("Erreur serveur, impossible de se connecter à la base de données.", "error")
        return redirect(url_for('register'))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    if cursor.fetchone():
        flash("Ce nom d'utilisateur existe déjà.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('register'))
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, password_hash))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Compte créé avec succès ! Vous pouvez maintenant vous connecter.", "success")
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        return process_login()

    nonce = secrets.token_hex(16)
    timestamp = int(time.time())
    session['nonce'] = nonce
    session['timestamp'] = timestamp
    return render_template('login.html', nonce=nonce, timestamp=timestamp)

@anti_replay_required
def process_login():
    captcha_input = request.form.get('captcha', '').upper()
    if 'captcha_text' not in session or captcha_input != session.get('captcha_text', '').upper():
        flash("Captcha incorrect.", "error")
        return redirect(url_for('login'))
    session.pop('captcha_text', None)

    username = request.form.get('username')
    password = request.form.get('password')
    conn = get_db_connection()
    if not conn:
        flash("Erreur serveur, impossible de vérifier les identifiants.", "error")
        return redirect(url_for('login'))
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user_data = cursor.fetchone()
    if not user_data or not check_password_hash(user_data['password_hash'], password):
        flash("Identifiants incorrects.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('login'))

    if user_data['otp_secret']:
        session['user_id_2fa_pending'] = user_data['id']
        cursor.close()
        conn.close()
        return redirect(url_for('verify_2fa'))

    user_obj = User(id=user_data['id'], username=user_data['username'], otp_secret=user_data['otp_secret'])
    login_user(user_obj)
    cursor.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s", (user_data['id'],))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    if 'user_id_2fa_pending' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        return process_verify_2fa()

    nonce = secrets.token_hex(16)
    timestamp = int(time.time())
    session['nonce'] = nonce
    session['timestamp'] = timestamp
    return render_template('verify_2fa.html', nonce=nonce, timestamp=timestamp)

@anti_replay_required
def process_verify_2fa():
    user_id = session['user_id_2fa_pending']
    token = request.form.get('token')
    conn = get_db_connection()
    if not conn:
        flash("Erreur serveur.", "error")
        return redirect(url_for('verify_2fa'))

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    totp = pyotp.TOTP(user_data['otp_secret'])
    if totp.verify(token):
        session.pop('user_id_2fa_pending', None)
        user_obj = User(id=user_data['id'], username=user_data['username'], otp_secret=user_data['otp_secret'])
        login_user(user_obj)
        cursor.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s", (user_data['id'],))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
    else:
        flash("Code 2FA incorrect.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('verify_2fa'))

# --- Routes protégées (setup 2fa, dashboard, etc. inchangées) ---

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Vous avez été déconnecté.", "success")
    return redirect(url_for('login'))

@app.route('/setup-2fa')
@login_required
def setup_2fa():
    # ... (code inchangé) ...
    secret = pyotp.random_base32()
    conn = get_db_connection()
    if not conn:
        flash("Erreur serveur, impossible de configurer le 2FA.", "error")
        return redirect(url_for('dashboard'))
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET otp_secret = %s WHERE id = %s", (secret, current_user.id))
    conn.commit()
    cursor.close()
    conn.close()
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=current_user.username, issuer_name='TestVault App')
    img = qrcode.make(totp_uri)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    qr_code_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return render_template('setup_2fa.html', secret=secret, qr_code=qr_code_b64)

@app.route('/')
@login_required
def dashboard():
    # ... (code inchangé) ...
    try:
        conn = get_db_connection()
        if not conn:
            return "Erreur de connexion à la base de données", 500
        cursor = conn.cursor()
        cursor.execute("SELECT id, titre FROM livre")
        livres = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('index.html', livres=livres, user=current_user)
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)