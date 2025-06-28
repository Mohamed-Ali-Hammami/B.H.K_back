from .db_config import get_user_details_by_wallet_id
from web3 import Web3
from .db_setup import get_db_connection
from dotenv import load_dotenv
import os
from .handle_token import get_tanacoin_rate
import requests
from decimal import Decimal  # Importing Decimal for accurate fixed-point arithmetic

load_dotenv()
INFURA_PROJECT_ID = os.getenv('INFURA_PROJECT_ID')
USDT_CONTRACT_ADDRESS = '0xdac17f958d2ee523a2206206994597c13d831ec7'
TRANSFER_SIGNATURE = bytes.fromhex('a9059cbb')
RECEIVER_ADDRESS = os.getenv('RECEIVER_ADDRESS')
RECEIVER_BTC_ADDRESS=  os.getenv('RECEIVER_BTC_ADDRESS')
RECEIVER_USDT_ADDRESS=  os.getenv('RECEIVER_USDT_ADDRESS')
BLOCKCYPHER_API_BASE_URL = "https://api.blockcypher.com/v1/btc/main"
infura_url = INFURA_PROJECT_ID
web3 = Web3(Web3.HTTPProvider(infura_url))


def get_coin_gecko_rates():
    try:
        print("Fetching CoinGecko rates for BTC, ETH, and USDT in EUR.")
        
        # Call CoinGecko API for BTC, ETH, and USDT in EUR
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether&vs_currencies=eur'
        )
        response.raise_for_status()  # Raise an error for bad status codes
        data = response.json()
        print('data', data)
        
        btc_rate_eur = Decimal(data['bitcoin']['eur'])  # data {'bitcoin': {'eur': 90918}, 'ethereum': {'eur': 3253.09}, 'tether': {'eur': 0.957796}}
        eth_rate_eur = Decimal(data['ethereum']['eur'])  # ETH to EUR rate (convert to Decimal)
        usdt_rate_eur = Decimal(data['tether']['eur'])  # USDT to EUR rate (convert to Decimal)

        print(f"Fetched rates: BTC = {btc_rate_eur} EUR, ETH = {eth_rate_eur} EUR, USDT = {usdt_rate_eur} EUR")
        
        return btc_rate_eur, eth_rate_eur, usdt_rate_eur
    except requests.RequestException as e:
        print(f"Error fetching CoinGecko data: {e}")
        return None, None, None


def get_tanacoin_rates_in_crypto():
    print("Fetching Tanacoin rates in EUR, ETH, USDT, and BTC.")
    
    # Fetch Tanacoin rate in EUR from the database
    tanacoin_info = get_tanacoin_rate()
    print('tanacoin_info rate', tanacoin_info)
    if not tanacoin_info:
        print("Tanacoin info not found in the database.")
        return None, None, None, None  # Return None if Tanacoin info is not available
    
    try:
        tanacoin_rate_eur = Decimal(tanacoin_info)  # Convert Tanacoin rate to Decimal
        print(f"Tanacoin rate in EUR: {tanacoin_rate_eur}")
    except (ValueError, TypeError):
        print("Invalid Tanacoin rate format. Ensure it's a valid number.")
        return None, None, None, None

    # Fetch the exchange rates for ETH, USDT, and BTC in EUR
    try:
         
        btc_rate_eur, eth_rate_eur, usdt_rate_eur = get_coin_gecko_rates()
        print(f"Rates: ETH={eth_rate_eur}, USDT={usdt_rate_eur}, BTC={btc_rate_eur}")
    except Exception as e:
        print(f"Error fetching rates from CoinGecko: {e}")
        return None, None, None, None

    if not all([btc_rate_eur, eth_rate_eur, usdt_rate_eur]):
        print("One or more rates are missing or invalid.")
        return None, None, None, None

    # Safeguard against zero rates
    if eth_rate_eur == 0 or usdt_rate_eur == 0 or btc_rate_eur == 0:
        print("Error: One or more rates from CoinGecko are zero.")
        return None, None, None, None

    # Convert the Tanacoin rate in EUR to ETH, USDT, and BTC
    tanacoin_rate_eth = tanacoin_rate_eur / Decimal(eth_rate_eur)
    tanacoin_rate_usdt = tanacoin_rate_eur / Decimal(usdt_rate_eur)
    tanacoin_rate_btc = tanacoin_rate_eur / Decimal(btc_rate_eur)

    print(f"Converted Tanacoin rates: {tanacoin_rate_eth} ETH, {tanacoin_rate_usdt} USDT, {tanacoin_rate_btc} BTC")
    
    return tanacoin_rate_eur, tanacoin_rate_eth, tanacoin_rate_usdt, tanacoin_rate_btc

# Updated get_btc_transaction_status function
def get_btc_transaction_status(tx_hash: str, added_percentage=0):  # Default value is now 0
    try:
        # Check if it's a BTC transaction first
        if tx_hash:  # Assuming a prefix to distinguish BTC transactions
            btc_tx_hash = tx_hash
            response = requests.get(f"{BLOCKCYPHER_API_BASE_URL}/txs/{btc_tx_hash}")
            print(response)
            
            if response.status_code == 200:
                tx_data = response.json()
                from_address = tx_data.get("inputs", [{}])[0].get("addresses", ["Unknown"])[0]
                to_address = tx_data.get("outputs", [{}])[0].get("addresses", ["Unknown"])[0]
                btc_value = Decimal(tx_data.get("outputs", [{}])[0].get("value", 0)) / Decimal(10 ** 8)  # Convert satoshis to BTC
                
                # Fetch BTC to Tanacoin rate
                tanacoin_rate_eur, tanacoin_rate_eth, tanacoin_rate_usdt, tanacoin_rate_btc = get_tanacoin_rates_in_crypto()
                
                if tanacoin_rate_btc is None:
                    print("Tanacoin rate for BTC not available.")
                    return {"status": "error", "message": "Tanacoin rate for BTC not available"}

                # Calculate Tanacoin purchased based on BTC value
                tanacoin_purchased = btc_value / tanacoin_rate_btc

                # Convert added_percentage to Decimal to ensure it's compatible with other Decimal operations
                added_percentage = Decimal(added_percentage)

                # Apply the added percentage if it's greater than 0 (meaning no promo code applied)
                if added_percentage > 0:  # Only apply if the percentage is greater than 0
                    tanacoin_purchased = tanacoin_purchased * (1 + added_percentage / Decimal(100))  # Apply promo discount

                print(f"BTC transaction: {btc_value} BTC, {tanacoin_purchased} Tanacoins purchased.")
                
                # Validate the transaction
                validate_transaction(btc_tx_hash, btc_value, "BTC", tanacoin_purchased, from_address, to_address)
                
                return {
                    "status": "confirmed",
                    "from": from_address,
                    "to": to_address,
                    "value": btc_value,
                    "tanacoin_purchased": tanacoin_purchased,
                    "type": "BTC"
                }
            else:
                print(f"BTC transaction not found or invalid transaction hash. Status code: {response.status_code}")
                return {"status": "error", "message": "BTC transaction not found or invalid transaction hash"}
    except Exception as e:
        print(f"Error fetching transaction status: {str(e)}")
        return {"status": "error", "message": f"Error fetching transaction status: {str(e)}"}



def get_transaction_status(tx_hash: str, added_percentage=0):  # Default value is now 0
    print(f"Fetching transaction status for tx_hash: {tx_hash}")
    
    try:
        transaction = web3.eth.get_transaction(tx_hash)
        print(transaction)
        if not transaction:
            print("Transaction not found or invalid transaction hash.")
            return {"status": "error", "message": "Transaction not found or invalid transaction hash"}
        
        from_address = transaction['from']
        to_address = transaction['to']
        value = Decimal(web3.from_wei(transaction['value'], 'ether'))  # ETH value in the transaction (convert to Decimal)

        print(f"Transaction details: from={from_address}, to={to_address}, value={value} ETH")

        # Get the Tanacoin rates in EUR, ETH, and USDT
        tanacoin_rate_eur, tanacoin_rate_eth, tanacoin_rate_usdt, tanacoin_rate_btc = get_tanacoin_rates_in_crypto()
        
        # If Tanacoin rates are not available, return an error
        if tanacoin_rate_eur is None:
            print("Tanacoin rate not available.")
            return {"status": "error", "message": "Tanacoin rate not available"}
        
        # Check if it's a USDT transaction
        if to_address.lower() != USDT_CONTRACT_ADDRESS.lower():
            input_data = transaction.get('input', '')
            print('input_data', input_data)
            if input_data.startswith(TRANSFER_SIGNATURE): 
                print('CHECKING USDT TRANSACTION')  # Compare directly with hex string
                currency = 'USDT'
                # Parse the amount of USDT transferred from the raw transaction data
                usdt_value = web3.to_int(input_data[-32:])
                # Amount of USDT transferred (raw data, skip function signature)
                usdt_value = Decimal(usdt_value) / Decimal(10 ** 6)  # USDT has 6 decimals (convert to Decimal)
                tanacoin_purchased = usdt_value / tanacoin_rate_usdt  # Calculate how many Tanacoins were bought in USDT

                # Convert added_percentage to Decimal to ensure it's compatible with other Decimal operations
                added_percentage = Decimal(added_percentage)

                # Apply the added percentage if it's greater than 0 (meaning no promo code applied)
                if added_percentage > 0:  # Only apply if the percentage is greater than 0
                    tanacoin_purchased = tanacoin_purchased * (1 + added_percentage / Decimal(100))  # Apply promo discount
                print(f"USDT transaction: {usdt_value} USDT, {tanacoin_purchased} Tanacoins purchased.")
                validate_transaction(tx_hash, usdt_value, currency, tanacoin_purchased, from_address, to_address)
                
                return {
                    "status": "confirmed",
                    "from": from_address,
                    "to": to_address,
                    "value": usdt_value,
                    "tanacoin_purchased": tanacoin_purchased,
                    "type": "USDT"
                }

        # Check if it's an ETH transaction
        if to_address:
            currency = 'ETH'
            eth_value = value  # ETH value in the transaction
            tanacoin_purchased = eth_value / tanacoin_rate_eth 
            
            # Convert added_percentage to Decimal to ensure it's compatible with other Decimal operations
            added_percentage = Decimal(added_percentage)

            # Apply the added percentage if it's greater than 0 (meaning no promo code applied)
            if added_percentage > 0:  # Only apply if the percentage is greater than 0
                tanacoin_purchased = tanacoin_purchased * (1 + added_percentage / Decimal(100))  # Apply promo discount
            print(f"ETH transaction: {eth_value} ETH, {tanacoin_purchased} Tanacoins purchased.")
            validate_transaction(tx_hash, eth_value, currency, tanacoin_purchased, from_address, to_address)
            
            return {
                "status": "confirmed",
                "from": from_address,
                "to": to_address,
                "value": eth_value,
                "tanacoin_purchased": tanacoin_purchased,
                "type": "ETH"
            }

        # If no specific condition matches, we return pending status
        receipt = web3.eth.get_transaction_receipt(tx_hash)
        if receipt:
            if receipt['status'] == 1:
                print("Transaction confirmed.")
                return {"status": "confirmed", "from": from_address, "to": to_address, "value": value}
            else:
                print("Transaction failed.")
                return {"status": "failed", "from": from_address, "to": to_address, "value": value}
        else:
            print("Transaction pending.")
            return {"status": "pending", "from": from_address, "to": to_address, "value": value}
        
    except Exception as e:
        print(f"Error fetching transaction status: {str(e)}")
        return {"status": "error", "message": f"Error fetching transaction status: {str(e)}"}


def validate_transaction(tx_hash,value ,currency, tanacoin_purchased: Decimal, sender_address: str, expected_receiver_address: str):
    try:
        if expected_receiver_address != RECEIVER_ADDRESS or expected_receiver_address != RECEIVER_BTC_ADDRESS or expected_receiver_address != RECEIVER_USDT_ADDRESS:
            print("ERROR WRONG ADDRESS")
            return {"status": "error", "message": "Invalid Transaction receiver address and expected receiver address do not match"}
        else:
            validate_trx = store_transaction_in_db(tx_hash,value,currency,sender_address, tanacoin_purchased)
            return validate_trx
        
    except Exception as e:
        print(f"Error in validate_transaction: {str(e)}")
        return {"status": "error", "message": f"Error in validation: {str(e)}"}

def store_transaction_in_db(tx_hash, value, currency, sender_address, tanacoin_purchased):
    connection = None
    try:
        print("Starting to retrieve user details...")  # Added print statement
        userdetails = get_user_details_by_wallet_id(sender_address)  
        
        if userdetails:  # Check if the result is not empty
            user_id = userdetails[0].get("id")  # Access the first dictionary in the list
            print(f"User ID: {user_id}")  # Print the user ID
        else:
            print("No user details found.")
            return False, "No user found with provided wallet ID."
        
        crypto_precision = 18

        connection = get_db_connection()

        with connection.cursor() as cursor:
            # Prepare the stored procedure call
            stored_procedure = """
                CALL purchase_and_update_tanacoin(
                    %s, %s, %s, %s, %s, %s
                );
            """

            # Execute the stored procedure with the provided parameters
            cursor.execute(stored_procedure, (user_id, value, currency, crypto_precision, tx_hash, tanacoin_purchased))
            
            # Commit the transaction (important for changes to take effect)
            connection.commit()

            # Fetch the result message from the SELECT statement at the end of the stored procedure
            result = cursor.fetchone()
            print(result['message'])  # Print success message from the procedure
            
            # Optionally, check if there are specific return values or conditions:
            if result:
                print("Stored procedure executed successfully.")
            else:
                print("Stored procedure did not return any result.")
        
        print("Transaction stored successfully in the database.")  # Added print statement
        return True, "Transaction stored successfully"
    
    except Exception as e:
        print(f"Error occurred during transaction storage: {e}")  # More descriptive error print
        return False, str(e)
    
    finally:
        if connection:
            connection.close()
