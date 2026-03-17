import pyodbc
from flask import jsonify

def get_db_connection():
    conn = pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=localhost;'
        'DATABASE=social-media-optimizer;'
        'UID=social-media-optimizer;'
        'PWD=social-media-optimizer'
    )
    return conn

def create_user_table():
    pass


def insert_new_user(username, email, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM Users WHERE Username = ? OR Email = ?', (username, email))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({'error': 'Username or email already exists'}), 409

        cursor.execute('''
            INSERT INTO Users (Username, PasswordHash, Email)
            VALUES (?, ?, ?)
        ''', (username, password, email))
        conn.commit()

        return jsonify({'message': 'User created successfully', 'redirect': '/login'}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()



def fetch_user(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT PasswordHash FROM Users WHERE Username = ?', (username,))
    return cursor.fetchone()


def insert_data_to_database(df):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM Users WHERE Username = ? OR Email = ?', (username, email))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({'error': 'Username or email already exists'}), 409

        cursor.execute('''
            INSERT INTO Users (Username, PasswordHash, Email)
            VALUES (?, ?, ?)
        ''', (username, password, email))
        conn.commit()

        return jsonify({'message': 'User created successfully', 'redirect': '/login'}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

def create_comments_table():
    pass