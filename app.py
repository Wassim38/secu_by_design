from flask import Flask, render_template
import mysql.connector
import hvac
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)

def get_vault_credentials():
    vault_addr = os.environ.get('VAULT_ADDR')
    vault_token = os.environ.get('VAULT_TOKEN')
    if not vault_addr or not vault_token:
        raise ValueError("VAULT_ADDR or VAULT_TOKEN environment variable is not set")
    client = hvac.Client(url=vault_addr, token=vault_token)
    if not client.is_authenticated():
        raise ValueError("Failed to authenticate with Vault")
    secret = client.secrets.kv.read_secret_version(path='testvault')['data']['data']
    return secret['db_user'], secret['db_password']

def get_db_connection():
    db_user, db_password = get_vault_credentials()
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST'),
        port=int(os.environ.get('DB_PORT')),
        user=db_user,
        password=db_password,
        database=os.environ.get('DB_NAME')
    )

@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, titre FROM livre")
        livres = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('index.html', livres=livres)
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)