from flask import Flask
import os
import pymysql
from dotenv import load_dotenv
from flask_cors import CORS
from pymysql.cursors import DictCursor
import logging

load_dotenv()

# Path for SSL certificates, if needed
SSL_CA_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def get_db_connection():
    """Establish and return a database connection."""
    try:
        # Ensure all necessary environment variables are set
        required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_PORT']
        for var in required_vars:
            if not os.getenv(var):
                raise EnvironmentError(f"Environment variable {var} is not set.")

        logger.info("Attempting to connect to the database...")

        connection = pymysql.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            db=os.getenv('DB_NAME'),
            charset='utf8mb4',
            port=int(os.getenv('DB_PORT')),
            cursorclass=DictCursor,
            connect_timeout=10  # Set a connection timeout (in seconds)
        )
        logger.info("Database connection successful.")
        return connection
    except pymysql.MySQLError as e:
        logger.error(f"Database connection failed: {e}")
        raise RuntimeError(f"Database connection failed: {e}") from e
    except EnvironmentError as env_error:
        logger.error(f"Environment variable missing: {env_error}")
        raise env_error
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise RuntimeError(f"An unexpected error occurred: {e}") from e
    
def init_db(app):
    """Initialize the database and app configurations."""
    print("Initializing database connection...")
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'images')
    print(f"Upload folder set to: {app.config['UPLOAD_FOLDER']}")
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Test the database connection
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            print("Checking database connection with a simple query...")
            cursor.execute('SELECT 1')
        connection.close()
        print("Database connection successful.")
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        raise RuntimeError("Could not connect to the database.") from e
    finally:
        if connection:
            connection.close()  # Make sure to close the connection manually
            print("Database connection closed.")
def create_app():
    """Create and return the Flask application."""
    print("Creating Flask app...")
    app = Flask(__name__)  # No need for static_folder or static_url_path
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')
    CORS(app)  # Allow cross-origin requests from your frontend server
    print(f"App secret key: {app.secret_key}")
    return app
