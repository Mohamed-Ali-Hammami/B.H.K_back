from .db_setup import get_db_connection
import pymysql
import logging
import os
import uuid

class KYCService:
    def __init__(self, db_connection):
        self.db = db_connection
        self.allowed_extensions = {'png', 'jpg', 'jpeg', 'pdf'}
        self.upload_folder = os.path.join(os.path.dirname(__file__), '..', 'Uploads', 'kyc_documents')
        os.makedirs(self.upload_folder, exist_ok=True)
        self.valid_document_types = ['id_front', 'id_back', 'selfie', 'proof_of_address', 'passport', 'other']

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.allowed_extensions

    async def save_document(self, file, user_id, document_type):
        """Save KYC document and return file path"""
        if not file or not self.allowed_file(file.filename):
            return None, f"Invalid file type. Allowed types: {', '.join(self.allowed_extensions)}"

        if document_type not in self.valid_document_types:
            return None, "Invalid document type"

        # Create appropriate folder based on whether user_id is provided
        if user_id == 'temp':
            # For temporary uploads before user creation
            save_folder = os.path.join(self.upload_folder, 'temp')
        else:
            # For user-specific uploads
            save_folder = os.path.join(self.upload_folder, str(user_id))
            
        os.makedirs(save_folder, exist_ok=True)

        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{document_type}_{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(save_folder, filename)

        try:
            file.save(filepath)
            return filepath, None
        except Exception as e:
            return None, f"Error saving file: {str(e)}"

    async def upload_kyc_document(self, user_id, document_type, file):
        """Handle KYC document submission"""
        # Save the document
        is_temp = user_id is None or isinstance(user_id, str) and user_id.startswith('temp_')
        filepath, error = await self.save_document(file, 'temp' if is_temp else user_id, document_type)
        if error:
            return False, error

        # Record in database
        try:
            with self.db.cursor() as cursor:
                if is_temp:
                    # For temporary users, store in a separate table or with a NULL user_id
                    cursor.execute('''
                        INSERT INTO temp_kyc_documents 
                        (temp_user_id, document_type, file_path, status, created_at, updated_at)
                        VALUES (%s, %s, %s, 'pending', NOW(), NOW())
                        ON DUPLICATE KEY UPDATE
                            file_path = VALUES(file_path),
                            status = 'pending',
                            updated_at = NOW()
                    ''', (user_id, document_type, filepath))
                else:
                    # For registered users, store in the regular kyc_documents table
                    cursor.execute('''
                        SELECT id FROM kyc_documents 
                        WHERE user_id = %s AND document_type = %s
                    ''', (user_id, document_type))
                    
                    if cursor.fetchone():
                        # Update existing document
                        cursor.execute('''
                            UPDATE kyc_documents 
                            SET file_path = %s, 
                                status = 'pending',
                                rejection_reason = NULL,
                                verified_by = NULL,
                                verified_at = NULL,
                                updated_at = NOW()
                            WHERE user_id = %s AND document_type = %s
                        ''', (filepath, user_id, document_type))
                    else:
                        cursor.execute('''
                            INSERT INTO kyc_documents 
                            (user_id, document_type, file_path, status, created_at, updated_at)
                            VALUES (%s, %s, %s, 'pending', NOW(), NOW())
                        ''', (user_id, document_type, filepath))
                
                self.db.commit()
                return True, "Document uploaded successfully"
                
        except Exception as e:
            self.db.rollback()
            logging.error(f"Error in upload_kyc_document: {str(e)}")
            return False, f"Database error: {str(e)}"

    async def get_kyc_status(self, user_id):
        """Get the current KYC status for a user"""
        try:
            with self.db.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute('''
                    SELECT document_type, status, created_at, updated_at
                    FROM kyc_documents 
                    WHERE user_id = %s
                ''', (user_id,))
                documents = cursor.fetchall()
                
                if not documents:
                    # Check for temporary documents if no regular documents found
                    cursor.execute('''
                        SELECT document_type, status, created_at, updated_at
                        FROM temp_kyc_documents 
                        WHERE temp_user_id = %s
                    ''', (f"temp_{user_id}",))
                    temp_documents = cursor.fetchall()
                    
                    if temp_documents:
                        return {
                            'status': 'in_progress',
                            'message': 'Documents uploaded but not yet linked to your account',
                            'documents': temp_documents
                        }
                    
                    return {
                        'status': 'not_started',
                        'message': 'No KYC documents submitted',
                        'documents': []
                    }
                
                # Determine overall status
                statuses = [doc['status'] for doc in documents]
                if 'rejected' in statuses:
                    status = 'rejected'
                elif 'pending' in statuses:
                    status = 'pending'
                elif all(s == 'approved' for s in statuses):
                    status = 'approved'
                else:
                    status = 'in_progress'
                
                return {
                    'status': status,
                    'documents': documents
                }
                
        except Exception as e:
            logging.error(f"Error in get_kyc_status: {str(e)}")
            return {'error': str(e)}

    async def link_temp_documents(self, temp_user_id, new_user_id):
        """Link temporary KYC documents to a new user ID after registration"""
        try:
            with self.db.cursor() as cursor:
                # Move files from temp to user directory
                temp_dir = os.path.join(self.upload_folder, 'temp')
                user_dir = os.path.join(self.upload_folder, str(new_user_id))
                os.makedirs(user_dir, exist_ok=True)
                
                # Move all files from temp to user directory
                for filename in os.listdir(temp_dir):
                    if filename.startswith(temp_user_id + '_'):
                        old_path = os.path.join(temp_dir, filename)
                        new_filename = filename.replace(temp_user_id + '_', '')
                        new_path = os.path.join(user_dir, new_filename)
                        os.rename(old_path, new_path)
                
                # Update database records
                cursor.execute('''
                    UPDATE kyc_documents 
                    SET user_id = %s, updated_at = NOW()
                    WHERE user_id = %s
                ''', (new_user_id, temp_user_id))
                
                # Clean up temp records
                cursor.execute('''
                    DELETE FROM temp_kyc_documents 
                    WHERE temp_user_id = %s
                ''', (temp_user_id,))
                
                self.db.commit()
                return True, "KYC documents successfully linked to your account"
                
        except Exception as e:
            self.db.rollback()
            logging.error(f"Error in link_temp_documents: {str(e)}")
            return False, f"Failed to link KYC documents: {str(e)}"

    async def verify_document(self, user_id, document_type, status, verified_by, rejection_reason=None):
        """Admin function to verify a document"""
        try:
            with self.db.cursor() as cursor:
                cursor.execute('''
                    UPDATE kyc_documents 
                    SET status = %s,
                        verified_by = %s,
                        verified_at = NOW(),
                        rejection_reason = %s,
                        updated_at = NOW()
                    WHERE user_id = %s AND document_type = %s
                ''', (status, verified_by, rejection_reason, user_id, document_type))
                
                # Update user's ID verification status if all required documents are approved
                if status == 'approved':
                    cursor.execute('''
                        SELECT COUNT(*) as pending_count 
                        FROM kyc_documents 
                        WHERE user_id = %s AND status != 'approved'
                    ''', (user_id,))
                    
                    result = cursor.fetchone()
                    if result and result['pending_count'] == 0:
                        cursor.execute('''
                            UPDATE user_profiles 
                            SET id_verified = TRUE 
                            WHERE user_id = %s
                        ''', (user_id,))
                
                self.db.commit()
                return True, "Document verification updated"
                
        except Exception as e:
            self.db.rollback()
            logging.error(f"Error in verify_document: {str(e)}")
            return False, f"Error updating document status: {str(e)}"

def upload_kyc_document(user_id, document_type, file):
    """Upload KYC document for verification"""
    connection = get_db_connection()
    try:
        kyc_service = KYCService(connection)
        success, message = asyncio.run(kyc_service.upload_kyc_document(user_id, document_type, file))
        return success, message
    except Exception as e:
        logging.error(f"Error in upload_kyc_document: {str(e)}")
        return False, str(e)
    finally:
        connection.close()