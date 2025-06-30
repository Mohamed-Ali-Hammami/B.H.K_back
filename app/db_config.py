import pymysql.cursors
from db_setup import get_db_connection
import logging
import base64
import pymysql

def encode_base64(data):
    """Encode bytes data to base64 string."""
    if isinstance(data, bytes):
        return base64.b64encode(data).decode('utf-8')
    return data
def get_superuser_details(identifier):
    logging.info(f"Fetching superuser details for identifier: {identifier}")
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = '''
            SELECT superuser_id, email, password_hash
            FROM superusers 
            WHERE superuser_id = %s OR email = %s
            '''
            cursor.execute(query, (identifier, identifier))
            superuser = cursor.fetchone()
            if superuser:
                logging.info(f"Superuser found: {superuser}")
            return superuser
    except Exception as e:
        logging.error(f"Error fetching superuser details: {e}")
        return None
    finally:
        connection.close()

def get_user_data(user_id):
    """Fetch user data from the database."""
    # Establish database connection
    connection = None
    try:
        connection = get_db_connection()
        print(f"[DEBUG] Database connection established for user_id: {user_id}")

        with connection.cursor() as cursor:
            # Call the stored procedure 'get_user_data' with the provided user_id
            cursor.callproc('get_user_data', [user_id])
            user_data = []
            transactions = []
            payments = []
            # Fetch all the results from the stored procedure
            for result in cursor.fetchall():
                # Convert bytes data (profile_picture, transaction_hash) to base64 string
                profile_picture = encode_base64(result['profile_picture'])
                
                transaction_hash = result['transaction_hash']
                if isinstance(transaction_hash, bytes):
                    transaction_hash = base64.b64encode(transaction_hash).decode('utf-8')

                # Collect user data
                user_data.append({
                    'user_id': result['user_id'],
                    'first_name': result['first_name'],
                    'last_name': result['last_name'],
                    'email': result['email'],
                    'profile_picture': profile_picture,
                    'tnc_wallet_id': result['user_tnc_wallet_id'],
                    'created_at': result['created_at']
                })

                # Collect transaction data
                if result['transaction_id']:
                    transactions.append({
                        'transaction_id': result['transaction_id'],
                        'sender_id': result['sender_id'],
                        'recipient_tnc_wallet_id': result['recipient_tnc_wallet_id'],
                        'amount': result['amount'],
                        'transaction_date': result['transaction_date'],
                        'status': result['status'],
                        'transaction_hash': transaction_hash
                    })

                # Collect payment data
                if result['payment_id']:
                    payments.append({
                        'payment_id': result['payment_id'],
                        'payment_amount': result['payment_amount'],
                        'crypto_type': result['crypto_type'],
                        'crypto_precision': result['crypto_precision'],
                        'payment_transaction_hash': result['payment_transaction_hash'],
                        'payment_date': result['payment_date'],
                        'payment_status': result['payment_status']
                    })

            # Return the formatted data in a dictionary
            return {
                'user_data': user_data,
                'transactions': transactions,
                'payments': payments
            }

    except pymysql.MySQLError as e:
        print(f"[ERROR] MySQL error: {e}")
    
    finally:
        if connection:
            connection.close()
            print("[DEBUG] Database connection closed.")
        
    return None
def get_all_user_details():
    # Get the database connection
    connection = get_db_connection()

    try:
        # Create a cursor object with DictCursor to get results as dictionaries
        with connection.cursor() as cursor:
            # Call the stored procedure
            cursor.callproc('GetAllUserDetails')

            # Initialize the list to store all the data and a dictionary to track unique users
            user_details = []
            seen_users = {}  # Dictionary to keep track of unique users by user_id
            
            # While there are result sets available
            while True:
                # Fetch the result set (if any) as a list of dictionaries
                result = cursor.fetchall()

                # Process the result only if there's data
                if result:
                    for row in result:
                        user_id = row['user_id']

                        # Skip adding the user if we have already seen this user_id
                        if user_id in seen_users:
                            continue  # Skip duplicates based on user_id

                        # Mark the user as seen
                        seen_users[user_id] = True

                        user_data = {
                            'user_id': row['user_id'],
                            'first_name': row['first_name'],
                            'last_name': row['last_name'],
                            'email': row['email'],
                            'profile_picture': row['profile_picture'],  # Added profile_picture here
                            'user_tnc_wallet_id': row['user_tnc_wallet_id'],
                            'user_created_at': row['user_created_at'],

                            'tnc_wallet_id': row['tnc_wallet_id'],
                            'tnc_wallet_balance': row['tnc_wallet_balance'],
                            'tnc_wallet_created_at': row['tnc_wallet_created_at'],

                            'crypto_payment_id': row['crypto_payment_id'],
                            'payment_amount': row['payment_amount'],
                            'crypto_type': row['crypto_type'],
                            'payment_transaction_hash': row['payment_transaction_hash'],
                            'payment_date': row['payment_date'],
                            'payment_status': row['payment_status'],
                            'tanacoin_quantity': row['tanacoin_quantity'],

                            # Tanacoin Transactions (Sender)
                            'tanacoin_transaction_id_sender': row['tanacoin_transaction_id_sender'],
                            'recipient_id_sender': row['recipient_id_sender'],
                            'amount_sent': row['amount_sent'],
                            'transaction_date_sent': row['transaction_date_sent'],
                            'transaction_hash_sent': row['transaction_hash_sent'],
                            'recipient_wallet_id_sent': row['recipient_wallet_id_sent'],
                            'transaction_status_sent': row['transaction_status_sent'],

                            # Tanacoin Transactions (Recipient)
                            'tanacoin_transaction_id_recipient': row['tanacoin_transaction_id_recipient'],
                            'sender_id_recipient': row['sender_id_recipient'],
                            'amount_received': row['amount_received'],
                            'transaction_date_received': row['transaction_date_received'],
                            'transaction_hash_received': row['transaction_hash_received'],
                            'transaction_status_received': row['transaction_status_received'],

                            # Promo Codes (Spent)
                            'promo_code_id_spent': row['promo_code_id_spent'],
                            'promo_code_spent': row['promo_code_spent'],
                            'added_tnc_percentage_spent': row['added_tnc_percentage_spent'],
                            'promo_code_start_date_spent': row['promo_code_start_date_spent'],
                            'promo_code_end_date_spent': row['promo_code_end_date_spent'],
                            'promo_code_creator_id_spent': row['promo_code_creator_id_spent'],

                            # Promo Codes (Created)
                            'promo_code_id_created': row['promo_code_id_created'],
                            'promo_code_created': row['promo_code_created'],
                            'added_tnc_percentage_created': row['added_tnc_percentage_created'],
                            'promo_code_start_date_created': row['promo_code_start_date_created'],
                            'promo_code_end_date_created': row['promo_code_end_date_created'],
                            'promo_code_spender_id_created': row['promo_code_spender_id_created'],
                        }

                        user_details.append(user_data)

                # If no more result sets, break the loop
                if not cursor.nextset():
                    break

            # Now user_details is a list of dictionaries that you can return, print, or process further
            return user_details

    except pymysql.MySQLError as e:
        print(f"Error: {e}")
    finally:
        # Ensure the connection is closed
        connection.close()

