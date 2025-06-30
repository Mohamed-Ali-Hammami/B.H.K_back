from flask import request, jsonify, session,make_response,logging
from functools import wraps
import os
from db_config import get_user_data,get_all_user_details,get_db_connection
from user_management import (add_bonus_to_creator,get_promo_codes_by_creator,register_user, login_user,
                             upload_profile_picture,change_email,change_password,get_user_by_email)
from dotenv import load_dotenv
from wallet_communications import get_transaction_status,get_btc_transaction_status
import jwt
from db_setup import create_app
from handle_token import create_promo_code, update_spender_id, transfer_tanacoin,check_promocode_status
from self_utils import generate_promo_code
import base64
from send_mail import send_password_reset_email,send_contact_email
from kyc_handler import KYCService
import asyncio
load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY')
RECEIVER_ADDRESS = os.getenv("RECEIVER_ADDRESS")
INFURA_API_KEY = os.getenv("INFURA_API_KEY")
app = create_app()

# Function to validate the JWT token
def token_required(f):
    @wraps(f)
    def decorated():
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({"message": "Token is missing"}), 401
        try:
            token = token.split(" ")[1] if " " in token else token
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            current_user = {
                "user_id": payload.get('user_id'),
                "is_superuser": payload.get('is_superuser', False)
            }
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 403
        return f(current_user)
    return decorated
@app.route('/dashboard', methods=['GET', 'POST'])
@token_required
def dashboard(current_user):
    user_id = current_user['user_id']  # Get user ID from the decoded token
    user_details = get_user_data(user_id)

    if not user_details or not user_details['user_data']:
        return jsonify({"error": "User data could not be retrieved."}), 404

    if request.method == 'POST':
        action = request.json.get('action')  # Get action from JSON body

        if action == 'transfer':
            try:
                recipient_tnc_wallet_id = request.json.get('recipient_tnc_wallet_id')
                amount = float(request.json.get('amount'))
                result = transfer_tanacoin(user_id, recipient_tnc_wallet_id, amount)
                print(result)
                # Extracting message and status code from the result
                message = result[0]['message']
                status_code = result[1]
                return jsonify({'message': message}), status_code
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid input for transfer.'}), 400

        elif action == 'add_promo_code':
            print('add promocode action called ')
            try:
                creator_id = user_id  # The user creating the promo code is the current user
                # Generate promo code values
                promo_code, added_tnc_percentage, start_date, end_date = generate_promo_code()
                
                # Now add the generated promo code to the database
                create_promo_code(promo_code, added_tnc_percentage, start_date, end_date, creator_id)

                return jsonify({'message': f'Promo code {promo_code} crée avec succée!','added_tnc_percentage':added_tnc_percentage,'promo_code':promo_code}), 200

            except Exception as e:
                return jsonify({'error': f'An error occurred while creating promo code: {str(e)}'}), 500

        elif action == 'get_promo_codes':
            print('getpromocode called')
            try:
                promocodes = get_promo_codes_by_creator(user_id)
                
                # Format the response to return the promo codes
                promo_list = []
                for code in promocodes:
                    promo_list.append({
                        'code': code['code'],
                        'added_tnc_percentage': float(code['added_tnc_percentage']),  # Ensure decimal is converted to float
                        'start_date': code['start_date'].strftime('%Y-%m-%d %H:%M:%S'),  # Convert datetime to string
                        'end_date': code['end_date'].strftime('%Y-%m-%d %H:%M:%S'),  # Convert datetime to string
                        'created_at': code['created_at'].strftime('%Y-%m-%d %H:%M:%S'),  # Convert datetime to string
                    })

                return jsonify({'promocodes': promo_list}), 200
            except Exception as e:
                return jsonify({'error': f'An error occurred while retrieving promo codes: {str(e)}'}), 500

    return jsonify({
        "user_data": user_details['user_data'],
        "wallet_data": user_details['wallet_data'] if user_details['wallet_data'] else [],
        "transactions": user_details['transactions'] if user_details['transactions'] else [],
        "payments": user_details['payments'] if user_details['payments'] else []
    })

@app.route('/dashboard/data', methods=['GET', 'PUT'])
@token_required
def dashboard_data(current_user):
    user_id = current_user['user_id']  # Get user ID from the decoded token
    user_details = get_user_data(user_id)

    if not user_details or not user_details.get('user_data'):
        return jsonify({'error': 'User data not found'}), 404

    if request.method == 'PUT':
        data = request.json  
        changes_made = False
        errors = []

        # Extract and process profile picture
        profile_picture_base64 = data.get('profilePicture')
        if profile_picture_base64:
            try:
                profile_picture_blob = base64.b64decode(profile_picture_base64)
                result = upload_profile_picture(user_id, profile_picture_blob)
                if result:
                    changes_made = True
                else:
                    errors.append("Failed to upload profile picture.")
            except Exception as e:
                errors.append(f"Invalid profile picture format: {str(e)}")

        # Process email update
        new_email = data.get('email')
        if new_email:
            # Ensure email format is valid
            if '@' not in new_email or '.' not in new_email.split('@')[-1]:
                errors.append("Invalid email format.")
            else:
                result = change_email(user_id, new_email)
                if result:
                    changes_made = True
                else:
                    errors.append("Failed to update email.")

        # Process password update (without old password requirement)
        new_password = data.get('newPassword')

        if new_password:
            # Validate new password length
            if len(new_password) < 6:
                errors.append("New password must be at least 6 characters long.")
            else:
                result = change_password(user_id, new_password)
                if result:
                    changes_made = True
                else:
                    errors.append("Failed to update password.")

        # Response handling
        if changes_made:
            return jsonify({"message": "User details updated successfully."}), 200
        elif errors:
            return jsonify({"message": "Errors occurred", "errors": errors}), 400
        else:
            return jsonify({"message": "No changes were made."}), 400

    # Return the data with a proper structure for GET request
    return jsonify({
        "user_data": user_details.get('user_data'),
        "wallet_data": user_details.get('wallet_data', []),
        "transactions": user_details.get('transactions', []),
        "payments": user_details.get('payments', [])
    })
@app.route('/api/check_promo_code', methods=['POST'])
@token_required
def promocodevalidation(current_user):
    data = request.get_json()
    promo_code = data.get('promo_code')
    user_id = current_user['user_id']

    print(f"Checking promo code: {promo_code} for user_id: {user_id}")
    
    # Validate the promo code by calling the function
    validate_promocode = check_promocode_status(promo_code, user_id)
    print(f"Promo code validation result: {validate_promocode}")
    
    # Check if the promo code is valid and includes added_tnc_percentage
    if validate_promocode['status'] == 'valid' and 'added_tnc_percentage' in validate_promocode:
        return jsonify({
            'status': 'valid',
            'added_tnc_percentage': validate_promocode['added_tnc_percentage'],
            'message': 'Promo code applied successfully'
        }), 200
    else:
        # If promo code is invalid or no bonus is associated, return an error response
        return jsonify({
            'status': 'invalid',
            'message': validate_promocode.get('message', 'Invalid or expired promo code')
        }), 400

@app.route('/api/transaction-status', methods=['POST', 'GET'])
@token_required
def transaction_status(current_user):
    data = request.get_json()
    tx_hash = data.get('tx_hash')
    payment_method = data.get('payment_method')
    promo_code = data.get('promo_code')  # Optional
    user_id = current_user['user_id']

    if not tx_hash:
        return jsonify({"status": "error", "message": "Transaction hash is required"}), 400

    if not payment_method:
        return jsonify({"status": "error", "message": "Payment method is required"}), 400

    added_percentage = 0
    creator_id = None

    if promo_code:
        promo_status = check_promocode_status(promo_code, user_id)
        if promo_status.get('status') != 'valid':
            return jsonify({"status": "error", "message": promo_status.get('message', "Invalid or expired promo code")}), 400
        creator_id = promo_status.get('creator_id')
        added_percentage = float(promo_status.get('added_tnc_percentage', 0))

    try:
        result = None
        if payment_method == 'ETH':
            result = get_transaction_status(tx_hash, added_percentage)
        elif payment_method == 'BTC':
            result = get_btc_transaction_status(tx_hash, added_percentage)
        elif payment_method == 'USDT':
            result = get_transaction_status(tx_hash, added_percentage)
        else:
            return jsonify({"status": "error", "message": "Unsupported payment method"}), 400

        if result.get("status") == "confirmed" and added_percentage > 0:
            update_spender_id(promo_code, user_id)
            tanacoin_purchased = result.get("tanacoin_purchased", "0")
            add_bonus_to_creator(tanacoin_purchased, added_percentage, creator_id)

        return jsonify(result)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/signup', methods=['POST'])
def signup():
    """Handle user signup."""
    form_data = request.get_json()
    response, status_code = register_user(form_data)

    # Duplicate user error (MySQL 1062)
    if status_code == 1062:
        return jsonify({'message': response['message']}), 400
    # Success
    elif status_code == 201:
        # Return the full standardized structure (token, user, is_superuser, role)
        return jsonify(response), 201
    else:
        return jsonify({'message': response.get('message', 'An error occurred during registration.')}), status_code
@app.route('/kyc/upload', methods=['POST'])
def upload_kyc():
    user_id = request.form.get('user_id')
    document_type = request.form.get('document_type')
    file = request.files.get('file')
    if not all([user_id, document_type, file]):
        return jsonify({"message": "Missing required fields."}), 400
    connection = get_db_connection()
    kyc_service = KYCService(connection)
    success, message = asyncio.run(kyc_service.upload_kyc_document(user_id, document_type, file))
    connection.close()
    return jsonify({"success": success, "message": message}), 200 if success else 400

@app.route('/api/superuser-dashboard', methods=['GET', 'PUT'])
@token_required
def superuser_dashboard(current_user):
    if not current_user.get('is_superuser', False):
        return jsonify({"message": "Unauthorized access. Admins only."}), 403

    try:
        if request.method == 'GET':
            # Initialize the list to hold all user data
            dashboard_data = []

            # Fetch all user details using the updated function
            all_users = get_all_user_details()

            for user in all_users:
                # Convert profile_picture from bytes to base64 string if it's not None
                profile_picture_base64 = None
                if user['profile_picture']:
                    profile_picture_base64 = base64.b64encode(user['profile_picture']).decode('utf-8')

                # Map the data from `get_all_user_details()` to the response format
                user_data = {
                    "user_id": user['user_id'],
                    "first_name": user['first_name'],
                    "last_name": user['last_name'],
                    "email": user['email'],
                    "profile_picture": profile_picture_base64,  # Base64 encoded image
                    "user_created_at": user['user_created_at'],
                    "wallet_id": user['wallet_id'],
                    "user_tnc_wallet_id": user['user_tnc_wallet_id'],
                    "tnc_wallet_id": user['tnc_wallet_id'],
                    "tnc_wallet_balance": user['tnc_wallet_balance'],
                    "tnc_wallet_created_at": user['tnc_wallet_created_at'],
                    "crypto_payment_id": user['crypto_payment_id'],
                    "payment_amount": user['payment_amount'],
                    "crypto_type": user['crypto_type'],
                    "payment_transaction_hash": user['payment_transaction_hash'],
                    "payment_date": user['payment_date'],
                    "payment_status": user['payment_status'],
                    "tanacoin_quantity": user['tanacoin_quantity'],

                    # Tanacoin Transactions (Sender)
                    "tanacoin_transaction_id_sender": user['tanacoin_transaction_id_sender'],
                    "recipient_id_sender": user['recipient_id_sender'],
                    "amount_sent": user['amount_sent'],
                    "transaction_date_sent": user['transaction_date_sent'],
                    "transaction_hash_sent": user['transaction_hash_sent'],
                    "recipient_wallet_id_sent": user['recipient_wallet_id_sent'],
                    "transaction_status_sent": user['transaction_status_sent'],

                    # Tanacoin Transactions (Recipient)
                    "tanacoin_transaction_id_recipient": user['tanacoin_transaction_id_recipient'],
                    "sender_id_recipient": user['sender_id_recipient'],
                    "amount_received": user['amount_received'],
                    "transaction_date_received": user['transaction_date_received'],
                    "transaction_hash_received": user['transaction_hash_received'],
                    "transaction_status_received": user['transaction_status_received'],

                    # Promo Codes (Spent)
                    "promo_code_id_spent": user['promo_code_id_spent'],
                    "promo_code_spent": user['promo_code_spent'],
                    "added_tnc_percentage_spent": user['added_tnc_percentage_spent'],
                    "promo_code_start_date_spent": user['promo_code_start_date_spent'],
                    "promo_code_end_date_spent": user['promo_code_end_date_spent'],
                    "promo_code_creator_id_spent": user['promo_code_creator_id_spent'],

                    # Promo Codes (Created)
                    "promo_code_id_created": user['promo_code_id_created'],
                    "promo_code_created": user['promo_code_created'],
                    "added_tnc_percentage_created": user['added_tnc_percentage_created'],
                    "promo_code_start_date_created": user['promo_code_start_date_created'],
                    "promo_code_end_date_created": user['promo_code_end_date_created'],
                    "promo_code_spender_id_created": user['promo_code_spender_id_created'],
                }

                # Append each user's data to the dashboard data list
                dashboard_data.append(user_data)

            # Prepare the response data
            response_data = {
                "users": dashboard_data,
                "total_users": len(dashboard_data),
            }

            return jsonify(response_data), 200

    except Exception as e:
        logging.error(f"Error in superuser dashboard: {e}")
        return jsonify({'message': 'An error occurred.'}), 500

        
@app.route('/login', methods=['POST'])
def login():
    """Handle user login."""
    data = request.json
    identifier = data.get('identifier')
    password = data.get('password')
    # Validate user credentials (email/password login)
    result, status_code = login_user(wallet_connect=False, identifier=identifier, password=password)

    if status_code == 200:
        # Return the full standardized structure (token, user, is_superuser, role)
        return jsonify(result), 200
    else:
        return jsonify({'message': result.get('message', 'Authentication failed')}), status_code
@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    if not data or 'email' not in data:
        return {"message": "Email is required"}, 400
    
    email = data['email']
    new_password = get_user_by_email(email)
    print("newpass" , new_password)
    if not new_password:
        return {"message": "User Not Found"}, 500
    
    email_sent = send_password_reset_email(new_password, email)
    
    if email_sent:
        return {"message": "Password reset email sent successfully"}, 200
    else:
        return {"message": "Failed to send password reset email"}, 500
    
@app.route('/connect_wallet', methods=['POST'])
def connect_wallet():
    data = request.json
    # Check if wallet address is provided
    wallet_address = data.get('wallet_address')
    if not wallet_address:
        return jsonify({"message": "Wallet address is required."}), 400
    wallet_address = data.get('wallet_address')
    print(wallet_address)
    chain_id = data.get('chain_id')
    print(chain_id)
    # Attempt to log in the user using the wallet address
    login_response = login_user(wallet_connect=True, wallet_address=wallet_address, chain_id=chain_id)
    if login_response[1] == 200:  # If login is successful
        return jsonify(login_response[0]), 200
    # If login fails, we assume the user is not registered and attempt to register
    data['wallet_connect'] = True
    registration_response = register_user(data)
    # Return the registration response
    return jsonify(registration_response[0]), registration_response[1]

@app.route("/logout")
def logout():
    """Log out the user and clear the session."""
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

@app.route("/about_us")
def about():
    """Provide info about the site."""
    return jsonify({"message": "About us information goes here"})

@app.route('/api/contact-us', methods=['POST', 'OPTIONS'])
def contact_us():
    if request.method == 'OPTIONS':
        return make_response('', 200)

    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided."}), 400

    name = data.get('name')
    email = data.get('email')
    message = data.get('message')

    if not name or not email or not message:
        return jsonify({"message": "Name, email, and message are required."}), 400

    email_sent = send_contact_email(name, email, message)
    if email_sent:
        return jsonify({"message": "Your message has been sent successfully!"}), 200
    else:
        return jsonify({"message": "Failed to send your message. Please try again later."}), 500
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)


