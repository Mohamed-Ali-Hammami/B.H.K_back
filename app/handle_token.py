from db_setup import get_db_connection
from pymysql import MySQLError
from datetime import datetime

# Function to call the 'ManageTanacoinSupply' procedure
def manage_tanacoin_supply(action, amount):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Calling the procedure with parameters 'action' and 'amount'
            cursor.callproc('ManageTanacoinSupply', (action, amount))
            
            # Fetch and print the updated balance after the operation
            cursor.execute('SELECT @total_balance')
            result = cursor.fetchone()
            print(f"Updated Balance: {result[0]}")
            connection.commit()
    except MySQLError as e:
        print(f"Error occurred: {e}")
    finally:
        connection.close()
        
def get_tanacoin_main_balance():
    connection = get_db_connection()  # Ensure this function is defined elsewhere to get the DB connection
    try:
        with connection.cursor() as cursor:
            # Call the stored procedure
            cursor.callproc('GetTanacoininfo')
            
            # Fetch the first result from the procedure
            result = cursor.fetchone()
            
            # Check if the result contains the expected keys
            if result and all(key in result for key in ['total_balance', 'tanacoin_rate', 'tanacoins_sold']):
                # Return the result as a dictionary for ease of access
                return {
                    'total_balance': result['total_balance'],
                    'tanacoin_rate': result['tanacoin_rate'],
                    'tanacoins_sold': result['tanacoins_sold']
                }
            else:
                print("Procedure returned unexpected result:", result)
                return None  # Return None if the result is not as expected
    except MySQLError as e:
        print(f"Error occurred: {e}")
        return None
    finally:
        connection.close()

def get_tanacoin_rate():
    # Call the existing function to get all Tanacoin information
    tanacoin_info = get_tanacoin_main_balance()
    
    if tanacoin_info and 'tanacoin_rate' in tanacoin_info:
        return tanacoin_info['tanacoin_rate']
    else:
        print("Error: Tanacoin rate not found")
        return None

def transfer_tanacoin(sender_id, recipient_tnc_wallet_id, amount):
    print(f"Initiating transfer: Sender ID = {sender_id}, recipient_tnc_wallet_id = {recipient_tnc_wallet_id}, Amount = {amount}")  # Print the function's inputs
    connection = get_db_connection()
    
    try:
        print("Connecting to the database...")  # Indicating the database connection attempt
        with connection.cursor() as cursor:
            print(f"Calling stored procedure 'transfer_tanacoin' with sender_id={sender_id}, recipient_tnc_wallet_id={recipient_tnc_wallet_id}, amount={amount}")  # Print the stored procedure parameters
            cursor.callproc('transfer_tanacoin', (sender_id, recipient_tnc_wallet_id, amount))
            result = cursor.fetchone()
            connection.commit()
            print(f"Transaction successful. Transaction hash: {result}")  # Print the transaction hash returned by the procedure
            return {"message": "Transaction effectuée avec succès", "transaction_hash": result}, 200

    except MySQLError as e:
        print(f"MySQL error occurred: {e}")  # Print MySQL-specific error message
        connection.rollback()
        return {"message": f"MySQL error occurred: {e}."}, 500

    finally:
        print("Closing database connection...")  # Indicating database connection closure
        connection.close()

def update_tanacoin_balance(transaction_amount):
    try:
        # Establish a database connection
        connection = get_db_connection()

        with connection:
            with connection.cursor() as cursor:
                # Call the stored procedure
                cursor.callproc('UpdateTanacoinBalance', (transaction_amount,))

                # Commit the transaction
                connection.commit()

                print(f"Successfully updated Tanacoin balance with transaction amount: {transaction_amount}")

    except MySQLError as e:
        # Handle MySQL errors
        print(f"Error occurred: {e}")

    finally:
        # Close the connection
        if connection:
            connection.close()
# Function to check promo code status
def check_promocode_status(promo_code, user_id):
    # Establish the connection to the database
    connection = get_db_connection()

    try:
        # Create a cursor to interact with the database
        cursor = connection.cursor()

        # Call the stored procedure
        cursor.callproc('check_promocode_status', (promo_code, user_id))

        # Fetch the result
        result = cursor.fetchone()
        print(result)
        # If the result is None, return an error message indicating that the promo code is invalid
        if result is None:
            return {'status': 'invalid', 'message': 'Promo code is either expired or not found.'}

        # Check if the creator is trying to use the promo code
        if result.get('creator_id') == user_id:
            return {'status': 'error', 'message': 'Le créateur du code promo ne peut pas l\'utiliser.'}

        # If the promo code is valid, format and return the result
        result['added_tnc_percentage'] = str(result.get('added_tnc_percentage', '0.00'))  # Convert Decimal to string

        # Handle datetime fields
        if isinstance(result.get('start_date'), datetime):
            result['start_date'] = result['start_date'].strftime('%Y-%m-%d %H:%M:%S')
        else:
            result['start_date'] = None

        if isinstance(result.get('end_date'), datetime):
            result['end_date'] = result['end_date'].strftime('%Y-%m-%d %H:%M:%S')
        else:
            result['end_date'] = None

        # Ensure 'creator_id' and 'spender_id' are properly returned
        result['creator_id'] = result.get('creator_id')
        result['spender_id'] = result.get('spender_id')

        return result

    except MySQLError as err:
        return {'status': 'error', 'message': f'Database error: {err}'}

    finally:
        # Close the cursor and connection to the database
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def create_promo_code(promo_code, added_tnc_percentage, start_date, end_date, creator_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Call the updated stored procedure
            cursor.callproc('create_promo_code', (promo_code, added_tnc_percentage, start_date, end_date, creator_id))
            
            # Commit the transaction to the database
            connection.commit()

            print(f"Promo code '{promo_code}' crée avec succée!")
    except Exception as e:
        print(f"Error lors de la création du code promo: {str(e)}")
    finally:
        connection.close()

# Function to call the stored procedure to update spender ID
def update_spender_id(p_code, p_spender_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Call the stored procedure
            cursor.callproc('update_spender_id', (p_code, p_spender_id))
            
            # Commit the transaction to the database
            connection.commit()

            # Check if any rows were updated (you can also check the row count)
            if cursor.rowcount > 0:
                print(f"Spender ID for promo code '{p_code}' updated successfully!")
            else:
                print(f"No promo code found with code '{p_code}'")
    except MySQLError as e:
        print(f"Error updating spender ID: {str(e)}")
    finally:
        connection.close()
        