from typing import Dict, Optional, Union, Tuple, List, Any
from werkzeug.security import generate_password_hash, check_password_hash
from .db_setup import get_db_connection
from .self_utils import generate_token
import pymysql
import logging
import os
import uuid
import re
from dotenv import load_dotenv
from .kyc_handler import KYCService
from datetime import datetime
from decimal import Decimal

# Initialize logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Define path for default profile picture
DEFAULT_PICTURE_PATH = os.path.join(os.path.dirname(__file__), 'static', 'images', 'default_profile_picture_.png')



def register_user(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Register a new user with the provided data."""
    connection = None
    try:
        with open(DEFAULT_PICTURE_PATH, 'rb') as f:
            default_picture = f.read()

        required_fields = [
            "first_name", "last_name", "date_of_birth", "email", "phone_number",
            "country", "address_line1", "city", "postal_code", "username", "password"
        ]
        
        if not all(data.get(field) for field in required_fields):
            logging.error("Missing required fields")
            return {"message": "Missing required fields."}, 400

        # Extract and validate data
        first_name = data["first_name"]
        last_name = data["last_name"]
        date_of_birth = data["date_of_birth"]
        email = data["email"]
        phone_number = data["phone_number"]
        country = data["country"]
        address_line1 = data["address_line1"]
        address_line2 = data.get("address_line2", "")
        city = data["city"]
        state = data.get("state", "")
        postal_code = data["postal_code"]
        username = data["username"]
        password_hash = generate_password_hash(data["password"])
        tnc_wallet_id = str(uuid.uuid4())

        # Validate date_of_birth
        try:
            datetime.strptime(date_of_birth, '%Y-%m-%d')
        except ValueError:
            return {"message": "Invalid date of birth format. Use YYYY-MM-DD."}, 400

        connection = get_db_connection()
        kyc_service = KYCService(connection)
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            args = (
                first_name, last_name, username, email, password_hash,
                default_picture, wallet_id, tnc_wallet_id, date_of_birth, phone_number, country,
                address_line1, address_line2, city, state, postal_code
            )
            logging.debug(f"Calling RegisterUser with args: {args}")
            cursor.callproc('RegisterUser', args)

            cursor.execute("SELECT LAST_INSERT_ID() as user_id")
            user_id = cursor.fetchone()["user_id"]
            logging.debug(f"New user_id: {user_id}")

            cursor.execute("SELECT is_superuser FROM users WHERE id = %s", (user_id,))
            is_superuser_row = cursor.fetchone()
            is_superuser = bool(is_superuser_row["is_superuser"]) if is_superuser_row else False
            role = "superuser" if is_superuser else "user"

            connection.commit()

            # KYC document handling can be added here if needed

            user_dict = {
                "user_id": user_id,
                "username": username,
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "id_verified": False,
                "is_superuser": is_superuser,
                "role": role
            }
            token = generate_token(user_id, is_superuser, role)
            return {
                "message": "Signup successful!",
                "token": token,
                "user": user_dict,
                "is_superuser": is_superuser,
                "role": role
            }, 201

    except pymysql.MySQLError as e:
        if connection:
            connection.rollback()
        error_message = str(e)
        logging.error(f"MySQL Error: {error_message}")
        if e.args[0] == 1062:
            if "username" in error_message:
                return {"message": "Username is already taken."}, 400
            elif "email" in error_message:
                return {"message": "Email is already registered."}, 400
            else:
                return {"message": "Duplicate entry error."}, 400
        return {"message": f"Database error: {error_message}"}, 500
    except Exception as e:
        if connection:
            connection.rollback()
        logging.error(f"Unexpected Error: {e}")
        return {"message": f"An unexpected error occurred: {str(e)}"}, 500
    finally:
        if connection:
            connection.close()



def check_credentials(identifier: str, password: str) -> Optional[Dict[str, Any]]:
    """Check if the provided credentials (username/email and password) are valid."""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT u.id, u.username, u.email, u.first_name, u.last_name, u.password_hash,
                       COALESCE(p.id_verified, FALSE) as id_verified,
                       COALESCE(u.is_superuser, 0) as is_superuser
                FROM users u
                LEFT JOIN user_profiles p ON u.id = p.user_id
                WHERE u.username = %s OR u.email = %s
            """, (identifier, identifier))
            user = cursor.fetchone()
            if user and check_password_hash(user["password_hash"], password):
                return {
                    "user_id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "first_name": user["first_name"],
                    "last_name": user["last_name"],
                    "id_verified": bool(user["id_verified"]),
                    "is_superuser": bool(user["is_superuser"]),
                    "role": "superuser" if user["is_superuser"] else "user"
                }
            return None
    except Exception as e:
        logging.error(f"Error checking credentials: {e}")
        return None
    finally:
        if connection:
            connection.close()

def login_user(**kwargs) -> Tuple[Dict[str, Any], int]:
    """Handle user login with email/username and password."""
    try:
        identifier = kwargs.get("identifier")
        password = kwargs.get("password")
        if not (identifier and password):
            return {"message": "Username/Email and password are required."}, 400
            
        user = check_credentials(identifier, password)
        if not user:
            return {"message": "Invalid credentials."}, 401

        token = generate_token(user["user_id"], user["is_superuser"], user["role"])
        return {
            "message": "Login successful!",
            "token": token,
            "user": user,
            "is_superuser": user["is_superuser"],
            "role": user["role"]
        }, 200
    except Exception as e:
        logging.error(f"Login error: {e}")
        return {"message": "An unexpected error occurred."}, 500

def get_user_by_email(email: str) -> Optional[str]:
    """Retrieve user by email and reset password for forgotten password flow."""
    import secrets
    import string
    
    connection = None
    try:
        # Generate a secure random password
        alphabet = string.ascii_letters + string.digits + string.punctuation
        new_password = ''.join(secrets.choice(alphabet) for _ in range(16))
        
        connection = get_db_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.callproc('get_user_by_email', (email,))
            user = cursor.fetchone()
            if user:
                hashed_password = generate_password_hash(new_password)
                cursor.callproc('update_forgotten_password', (email, hashed_password))
                connection.commit()
                return new_password
            return None
    except pymysql.MySQLError as e:
        logging.error(f"Error retrieving user by email: {e}")
        return None
    finally:
        if connection:
            connection.close()



def retrieve_user_data(user_id: int) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """Retrieve user details, transactions, and crypto payments."""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.callproc('GetUserDetails', (user_id,))
            results = {}
            results['user_info'] = cursor.fetchall()
            cursor.nextset()
            results['transactions'] = cursor.fetchall()
            cursor.nextset()
            results['crypto_payments'] = cursor.fetchall()
            return results
    except pymysql.MySQLError as e:
        logging.error(f"Error retrieving user data: {e}")
        return None
    finally:
        if connection:
            connection.close()

def upload_profile_picture(user_id: int, file: bytes) -> Tuple[bool, str]:
    """Upload a profile picture for a user."""
    if not file:
        return False, "No file provided."
    max_size = 50 * 1024 * 1024
    if len(file) > max_size:
        return False, "File size exceeds the 50MB limit."
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET profile_picture = %s WHERE id = %s", (file, user_id))
            connection.commit()
            return True, "Profile picture updated successfully."
    except pymysql.MySQLError as e:
        if connection:
            connection.rollback()
        return False, f"Database error: {e.args[1]}"
    except Exception as e:
        if connection:
            connection.rollback()
        return False, f"An error occurred: {str(e)}"
    finally:
        if connection:
            connection.close()

def change_username(user_id: int, new_username: str) -> Union[str, bool]:
    """Change a user's username if it is not already taken."""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.callproc('get_user_by_ID', (user_id,))
            user_info = cursor.fetchone()
            if not user_info:
                return "User not found."
            cursor.execute("SELECT username FROM users WHERE username = %s AND id != %s", (new_username, user_id))
            if cursor.fetchone():
                return f"Username '{new_username}' already exists."
            cursor.callproc('UpdateUsername', (user_id, new_username))
            connection.commit()
            return True
    except Exception as e:
        if connection:
            connection.rollback()
        return f"Error updating username: {str(e)}"
    finally:
        if connection:
            connection.close()

def is_valid_email(email: str) -> bool:
    """Validate email format using a regex pattern."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def change_email(user_id: int, new_email: str) -> Union[str, bool]:
    """Change a user's email if valid and not already registered."""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.callproc('get_user_by_ID', (user_id,))
            user_info = cursor.fetchone()
            if not user_info:
                return "User not found."
            if not is_valid_email(new_email):
                return "Invalid email format."
            cursor.execute("SELECT email FROM users WHERE email = %s AND id != %s", (new_email, user_id))
            if cursor.fetchone():
                return f"Email '{new_email}' is already registered."
            cursor.callproc('UpdateEmail', (user_id, new_email))
            connection.commit()
            return True
    except Exception as e:
        if connection:
            connection.rollback()
        return f"Error updating email: {str(e)}"
    finally:
        if connection:
            connection.close()

def change_password(user_id: int, new_password: str) -> bool:
    """Change a user's password."""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.callproc('get_user_by_ID', (user_id,))
            if not cursor.fetchone():
                return False
            new_password_hash = generate_password_hash(new_password)
            cursor.callproc('UpdatePassword', (user_id, new_password_hash))
            connection.commit()
            return True
    except Exception as e:
        if connection:
            connection.rollback()
        logging.error(f"Error updating password: {e}")
        return False
    finally:
        if connection:
            connection.close()

def get_promo_codes_by_creator(creator_id: int) -> Optional[List[Dict[str, Any]]]:
    """Retrieve promo codes created by a specific user."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        cursor.callproc('GetPromoCodesByCreator', (creator_id,))
        result = cursor.fetchall()
        if not result:
            logging.info(f"No promo codes found for creator_id {creator_id}.")
            return []
        return result
    except pymysql.MySQLError as e:
        logging.error(f"Error retrieving promo codes: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def add_bonus_to_creator(tanacoin_purchased: Decimal, added_percentage: Decimal, creator_id: int) -> None:
    """Add a bonus to the creator's wallet balance based on the promo code usage."""
    connection = None
    cursor = None
    try:
        tanacoin_value_without_promo = tanacoin_purchased / (1 + added_percentage / Decimal(100))
        tanacoin_bonus = tanacoin_purchased - tanacoin_value_without_promo
        logging.debug(f"Calculated bonus: {tanacoin_bonus} for creator_id: {creator_id}")

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE tnc_wallets
            SET balance = balance + %s
            WHERE user_id = %s
        """, (float(tanacoin_bonus), creator_id))
        connection.commit()

        if cursor.rowcount > 0:
            logging.info(f"Bonus of {tanacoin_bonus} added to creator {creator_id}'s balance.")
        else:
            logging.warning(f"Creator {creator_id} not found or balance update failed.")
    except pymysql.MySQLError as e:
        if connection:
            connection.rollback()
        logging.error(f"Error updating creator balance: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()