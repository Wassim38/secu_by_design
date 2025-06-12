from flask import Flask, render_template
import mysql.connector

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="testvault",
        password="securepassword123",
        database="testvault"
    )

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, titre FROM livre")
    livres = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', livres=livres)

if __name__ == '__main__':
    app.run(debug=True)