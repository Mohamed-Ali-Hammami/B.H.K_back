import random
import string
import re 
from dotenv import load_dotenv
import os
import hashlib
from datetime import datetime, timedelta
import jwt


load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_nonce')

def create_new_password(length=8) -> str:
    characters = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(random.choice(characters) for i in range(length))
    print(password)
    return password
def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None

def hash_password(password):
    salted_password = password + SECRET_KEY
    hashed_password = hashlib.sha256(salted_password.encode()).hexdigest()
    return hashed_password

def check_password(entered_password, stored_hash):
    entered_hash = hash_password(entered_password)

    return entered_hash == stored_hash

def generate_token(user_id, is_superuser, role):
    """
    Generate a JWT token for a user.
    Args:
        user_id (int): The user's ID.
        is_superuser (bool): Whether the user is a superuser.
        role (str): The user's role as a string ("user" or "superuser").
    Returns:
        str: The JWT token.
    """
    payload = {
        'user_id': user_id,
        'is_superuser': is_superuser,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')
def generate_promo_code():

    promo_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    added_tnc_percentage = 10.00
    start_date = datetime.now()
    end_date = start_date + timedelta(days=365)
    
    return promo_code, added_tnc_percentage, start_date, end_date