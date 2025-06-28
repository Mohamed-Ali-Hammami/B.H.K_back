import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from flask import logging
load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY')
def send_contact_email(name: str, email: str, message: str) -> bool:
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("RECIPIENT_EMAIL")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587)) 

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = f"Contact Us Form Submission from {name}"
        body = f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}"
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_password_reset_email(new_password, user_email: str) -> bool:
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))   
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = user_email
    msg['Subject'] = "Password Reset Request"
    body = f"Hello,\n\nYour password has been successfully reset. Your new password is:\n\n{new_password}\n\nPlease use this password to log in to your account. You may change it after logging in.\n\nBest regards,\nYour Website Team"
    msg.attach(MIMEText(body, 'plain'))
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, user_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False

def send_confirmation_email(user_email: str, confirm_link: str) -> bool:
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    if not all([sender_email, sender_password, smtp_server]):
        logging.error("Error: Missing required environment variables.")
        return False

    serializer = URLSafeTimedSerializer(SECRET_KEY)
    token = serializer.dumps({'email': user_email})
    allowed_origin = os.getenv('ALLOWED_ORIGIN', 'http://localhost:3000')
    confirm_link = f'{allowed_origin}/registration-confirmed/{token}'
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = user_email
    msg['Subject'] = "Confirm Your Registration"
    body = (
        f"Hello,\n\n"
        f"Please click the link below to confirm your registration:\n"
        f"{confirm_link}\n\n"
        f"This link will expire in one hour.\n\n"
        f"Best regards,\nYour Website Team"
    )
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, user_email, msg.as_string())
        return True
    except Exception as e:
        logging.error(f"Error sending confirmation email: {e}")
        return False