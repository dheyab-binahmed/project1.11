import os
import logging
import re
import PyPDF2
from PyPDF2 import PdfReader
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import pikepdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import mysql.connector
import subprocess
from concurrent.futures import ThreadPoolExecutor
from flask import abort
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Ghostscript compression 
def ghostscript_compress(input_pdf, output_pdf):
    gs_executable = r"C:\\Program Files\\gs\\gs10.04.0\\bin\\gswin64c.exe"
    gs_command = [
        gs_executable,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=/ebook",  #  quality: /screen, /ebook, /printer, /prepress
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={output_pdf}",
        input_pdf
    ]
    logging.debug("Running Ghostscript command: " + " ".join(gs_command))
    subprocess.run(gs_command, check=True)

# Database connection 
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='localhost',  
            user='root', 
            password='root', 
            database='user_data'
        )
        return conn
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        return None

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, username, password, is_admin):
        self.username = username
        self.password = password
        self.is_admin = is_admin

    def get_id(self):
        return self.username

@login_manager.user_loader
def load_user(username):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cursor:
            
            cursor.execute("SELECT username, password, is_admin FROM userdata WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            if user_data:
                return User(
                    username=user_data[0],
                    password=user_data[1],
                    is_admin=user_data[2]  
                )
            return None
    except Exception as e:
        logging.error(f"User load error: {e}")
        return None
    finally:
        conn.close()

# File History Logging
def log_file_history(username, filename, filepath, operation):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        file_size = os.path.getsize(filepath)  
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO FileHistory (username, filename, filepath, operation, size) VALUES (%s, %s, %s, %s, %s)",
                (username, filename, filepath, operation, file_size)
            )
            conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error logging file history: {e}")
        return False
    finally:
        conn.close()

# Routes
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        conn = get_db_connection() 
        if not conn:
            flash("Database connection error", "danger")
            return redirect(url_for('register'))
        try:
            with conn.cursor() as cursor:
                username = request.form['username'].strip()
                password = request.form['password'].strip()

                if len(username) == 0:
                    flash("Username cannot be empty.", "danger")
                    return redirect(url_for('register'))
                if len(password) < 8 or len(password) > 12:
                    flash("Password must be between 8-12 characters with at least one number.", "danger")
                    return redirect(url_for('register'))
                if not re.search(r'\d', password):
                    flash("Password must contain at least one number.", "danger")
                    return redirect(url_for('register'))

                cursor.execute("SELECT username FROM userdata WHERE username = %s", (username,))
                if cursor.fetchone():
                    flash("Username already taken.", "danger")
                    return redirect(url_for('register'))

                hashed_password = generate_password_hash(password)
                cursor.execute("INSERT INTO userdata (username, password) VALUES (%s, %s)", 
                               (username, hashed_password))
                conn.commit()
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for('login'))
        except Exception as e:
            logging.error(f"Registration error: {e}")
            flash("An error occurred during registration.", "danger")
            return redirect(url_for('register'))
        finally:
            conn.close()
    return render_template('register.html')

#login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return redirect(url_for('login'))
        try:
            with conn.cursor() as cursor:
                username = request.form['username'].strip()
                password = request.form['password'].strip()
                # Add is_admin to the query
                cursor.execute("SELECT username, password, is_admin FROM userdata WHERE username = %s", (username,))
                user_data = cursor.fetchone()
                if not user_data or not check_password_hash(user_data[1], password):
                    flash("Invalid username or password.", "danger")
                    return redirect(url_for('login'))
                # Pass is_admin to User constructor
                user = User(username=user_data[0], password=user_data[1], is_admin=user_data[2])
                login_user(user)
                return redirect(url_for('dashboard'))
        except Exception as e:
            logging.error(f"Login error: {e}")
            flash("An error occurred during login.", "danger")
            return redirect(url_for('login'))
        finally:
            conn.close()
    return render_template('login.html')



# check if the current user is an admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)  # Forbidden access
        return f(*args, **kwargs)
    return decorated_function



# List User Profiles Route
@app.route('/admin/profiles')
@login_required
@admin_required
def admin_profiles():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('dashboard'))  
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username FROM userdata")
            users = cursor.fetchall()  

        return render_template('admin_profiles.html', users=users)  
    except Exception as e:
        logging.error(f"Error fetching user profiles: {e}")
        flash("Error loading user profiles", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()


# Show User History Route
@app.route('/admin/user_history/<username>')
@login_required
@admin_required
def admin_user_history(username):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT filename, filepath, operation, timestamp, size FROM FileHistory WHERE username = %s",
                (username,)
            )
            history = cursor.fetchall()
        return render_template('admin_user_history.html', history=history, username=username)
    except Exception as e:
        logging.error(f"Error fetching user history: {e}")
        flash("Error loading user history", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

# User Profile Route
@app.route('/admin/update_profile/<username>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_update_profile(username):
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_password = request.form.get('password', '').strip()
        
        if not new_username:
            flash("Username cannot be empty", "danger")
            return redirect(url_for('admin_update_profile', username=username))
        
        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return redirect(url_for('dashboard'))
        
        try:
            with conn.cursor() as cursor:
                if new_username:
                    cursor.execute("UPDATE userdata SET username = %s WHERE username = %s", (new_username, username))
                if new_password:
                    hashed_password = generate_password_hash(new_password)
                    cursor.execute("UPDATE userdata SET password = %s WHERE username = %s", (hashed_password, username))
                conn.commit()
                flash("Profile updated successfully!", "success")
                return redirect(url_for('admin_profiles'))
        except Exception as e:
            logging.error(f"Error updating profile: {e}")
            flash("Error updating profile", "danger")
            return redirect(url_for('dashboard'))
        finally:
            conn.close()
    
    return render_template('admin_update_profile.html', username=username)


@app.route('/admin/user_stats/<username>')
@login_required
@admin_required
def admin_user_stats(username):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        with conn.cursor() as cursor:
            # Get account statistics
            cursor.execute(
                """SELECT 
                    COUNT(CASE WHEN operation = 'upload' THEN 1 END) AS total_uploads,
                    COUNT(CASE WHEN operation = 'compress' THEN 1 END) AS total_compressions,
                    COUNT(CASE WHEN operation = 'merge' THEN 1 END) AS total_combined_files,
                    COALESCE(SUM(size), 0) AS total_storage_used,
                    MAX(timestamp) AS last_activity
                FROM FileHistory 
                WHERE username = %s""",
                (username,)
            )
            stats = cursor.fetchone()

        return render_template(
            'admin_user_stats.html',
            username=username,
            total_uploads=stats[0],
            total_compressions=stats[1],
            total_combined_files=stats[2],
            total_storage=stats[3],
            last_activity=stats[4]
        )
    except Exception as e:
        logging.error(f"Error fetching user stats: {e}")
        flash("Error loading user statistics", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()
        
# Remove User Route
@app.route('/admin/remove_user/<username>')
@login_required
@admin_required
def admin_remove_user(username):
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        with conn.cursor() as cursor:
            # Delete related records in FileHistory first
            cursor.execute("DELETE FROM FileHistory WHERE username = %s", (username,))
            # Now delete the user
            cursor.execute("DELETE FROM userdata WHERE username = %s", (username,))
            conn.commit()
        flash(f"User '{username}' removed successfully!", "success")
        return redirect(url_for('admin_profiles'))
    except Exception as e:
        logging.error(f"Error removing user: {e}", exc_info=True)
        flash("Error removing user", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()


@app.route('/dashboard')
@login_required
def dashboard():
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return redirect(url_for('login'))
        
        with conn.cursor() as cursor:
            # Ensure user exists
            cursor.execute("SELECT username FROM userdata WHERE username = %s", (current_user.username,))
            user_record = cursor.fetchone()
            if not user_record:
                flash("User not found.", "danger")
                return redirect(url_for('login'))

            # Fetch user statistics
            cursor.execute(
                """SELECT 
                    COUNT(CASE WHEN operation = 'upload' THEN 1 END) AS total_uploads,
                    COUNT(CASE WHEN operation = 'compress' THEN 1 END) AS total_compressions,
                    COUNT(CASE WHEN operation = 'merge' THEN 1 END) AS total_combined_files,
                    COALESCE(SUM(size), 0) AS total_storage_used,
                    MAX(timestamp) AS last_activity
                FROM FileHistory 
                WHERE username = %s""",
                (current_user.username,)
            )
            stats = cursor.fetchone() or (0, 0, 0, 0, None)

            total_uploads, total_compressions, total_combined_files, total_storage, last_activity = stats
            
            # Handle last_activity being None
            if last_activity is None:
                last_activity = "N/A"

            # Admin statistics
            total_users = None
            admin_total_uploads = None
            admin_total_compressions = None
            if current_user.is_admin:
                cursor.execute("SELECT COUNT(*) FROM userdata")
                total_users = cursor.fetchone()[0]

                cursor.execute(
                    """SELECT 
                        COUNT(CASE WHEN operation = 'upload' THEN 1 END) AS total_uploads,
                        COUNT(CASE WHEN operation = 'compress' THEN 1 END) AS total_compressions
                    FROM FileHistory"""
                )
                admin_stats = cursor.fetchone() or (0, 0)
                admin_total_uploads, admin_total_compressions = admin_stats

        return render_template(
            'dashboard.html',
            username=user_record[0],
            total_uploads=total_uploads,
            total_compressions=total_compressions,
            total_combined_files=total_combined_files,
            total_storage=total_storage,
            last_activity=last_activity,
            total_users=total_users,
            admin_total_uploads=admin_total_uploads,
            admin_total_compressions=admin_total_compressions
        )
    except Exception as e:
        logging.error(f"Error fetching dashboard data: {e}")
        flash("Error loading dashboard", "danger")
        return redirect(url_for('login'))
    finally:
        conn.close()


       
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "danger")
            return redirect(url_for('profile'))
        try:
            with conn.cursor() as cursor:
                new_password = request.form['new_password'].strip()
                confirm_password = request.form['confirm_password'].strip()
                if new_password != confirm_password:
                    flash("New password and confirmation do not match.", "danger")
                    return redirect(url_for('profile'))
                if len(new_password) < 8 or len(new_password) > 12:
                    flash("Password must be between 8-12 characters.", "danger")
                    return redirect(url_for('profile'))
                if not re.search(r'\d', new_password):
                    flash("Password must contain at least one number.", "danger")
                    return redirect(url_for('profile'))
                hashed_password = generate_password_hash(new_password)
                cursor.execute("UPDATE userdata SET password = %s WHERE username = %s",
                               (hashed_password, current_user.username))
                conn.commit()
                flash("Password updated successfully!", "success")
                return redirect(url_for('profile'))
        except Exception as e:
            logging.error(f"Profile update error: {e}")
            flash("An error occurred while updating your profile.", "danger")
            return redirect(url_for('profile'))
        finally:
            conn.close()
    return render_template('profile.html', username=current_user.username)

@app.route('/file_history')
@login_required
def file_history():
    conn = get_db_connection()
    if not conn:
        logging.error("Failed to connect to the database")
        flash("Database connection error", "danger")
        return redirect(url_for('dashboard'))
    try:
        logging.debug(f"Fetching file history for user: {current_user.username}")
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT filename, filepath, operation, timestamp, size FROM FileHistory WHERE username = %s",
                (current_user.username,)
            )
            history = cursor.fetchall()
            if history:
                return render_template('file_history.html', history=history)
            else:
                flash("No file history found.", "info")
                return render_template('file_history.html', history=[])
    except Exception as e:
        logging.error(f"Error fetching file history: {e}")
        flash("Error loading file history", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/create_folder', methods=['POST'])
@login_required
def create_folder():
    foldername = request.form['foldername'].strip()
    if not foldername:
        flash("Folder name cannot be empty.", "danger")
        return redirect(url_for('dashboard'))
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('dashboard'))
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO FileOrganization (username, foldername, filepath) VALUES (%s, %s, %s)",
                (current_user.username, foldername, f"/{foldername}")
            )
            conn.commit()
        flash(f"Folder '{foldername}' created successfully!", "success")
        return redirect(url_for('dashboard'))
    except Exception as e:
        logging.error(f"Error creating folder: {e}")
        flash("Error creating folder", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/move_file', methods=['POST'])
@login_required
def move_file():
    filename = request.form['filename'].strip()
    foldername = request.form['foldername'].strip()
    if not filename or not foldername:
        flash("Filename and folder name are required.", "danger")
        return redirect(url_for('dashboard'))
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "danger")
        return redirect(url_for('dashboard'))
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE FileHistory SET filepath = %s WHERE username = %s AND filename = %s",
                (f"/{foldername}/{filename}", current_user.username, filename)
            )
            conn.commit()
        flash(f"File '{filename}' moved to folder '{foldername}'!", "success")
        return redirect(url_for('dashboard'))
    except Exception as e:
        logging.error(f"Error moving file: {e}")
        flash("Error moving file", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

# File Processing Routes 
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
BASE_PROCESSED_FOLDER = os.path.join(os.getcwd(), 'processed_files')
COMBINED_FOLDER = os.path.join(BASE_PROCESSED_FOLDER, 'combined_files')
COMPRESSED_FOLDER = os.path.join(BASE_PROCESSED_FOLDER, 'compressed_files')

app.config.update({
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'COMBINED_FOLDER': COMBINED_FOLDER,
    'COMPRESSED_FOLDER': COMPRESSED_FOLDER
})

for folder in [UPLOAD_FOLDER, COMBINED_FOLDER, COMPRESSED_FOLDER]:
    os.makedirs(folder, exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_valid_pdf(file_path):
    try:
        with open(file_path, 'rb') as f:
            reader = PdfReader(f)
            if len(reader.pages) > 0:
                return True
    except Exception as e:
        logging.error(f"Invalid PDF: {file_path}, Error: {e}")
    return False

def compress_pdf(input_pdf_path, output_pdf_path):
    try:
        logging.debug(f"Compressing PDF: {input_pdf_path} to {output_pdf_path}")
        with pikepdf.open(input_pdf_path) as pdf:
            logging.debug("PDF opened successfully. Optimizing images and streams...")
            for page_index, page in enumerate(pdf.pages):
                logging.debug(f"Processing page {page_index + 1}")
                resources = page.get('/Resources', None)
                if not resources:
                    logging.debug(f"No /Resources found on page {page_index + 1}.")
                    continue
                xobjects = resources.get('/XObject', None)
                if not xobjects:
                    logging.debug(f"No /XObject found on page {page_index + 1}.")
                    continue
                try:
                    xobjects = xobjects.get_object()
                except Exception as e:
                    logging.error(f"Error retrieving /XObject on page {page_index + 1}: {e}")
                    continue
                for key, xobj in xobjects.items():
                    try:
                        subtype = xobj.get('/Subtype')
                        if subtype != '/Image':
                            logging.debug(f"Skipping non-image XObject: {key}")
                            continue
                        filter_value = xobj.get('/Filter')
                        if filter_value == '/FlateDecode':
                            try:
                                xobj.write_to_bytes(compress_streams=True)
                                logging.debug(f"Compressed image: {key}")
                            except Exception as inner_e:
                                logging.error(f"Error compressing image {key} on page {page_index + 1}: {inner_e}")
                                continue
                        else:
                            logging.debug(f"XObject {key} has filter {filter_value}; skipping compression.")
                    except Exception as obj_e:
                        logging.error(f"Error processing XObject {key} on page {page_index + 1}: {obj_e}")
                        continue
            pdf.save(output_pdf_path, compress_streams=True)
            logging.debug(f"PDF saved successfully to {output_pdf_path}")
    except Exception as e:
        logging.error(f"Error compressing PDF: {e}")
        raise

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No files selected.', 'danger')
            return redirect(request.url)
        files = request.files.getlist('file')
        valid_files = []
        
        # Validate and save files
        for file in files:
            if file.filename == '':
                flash('One of the files has no name.', 'danger')
                return redirect(request.url)
            if not allowed_file(file.filename):
                flash('Invalid file type. Only PDFs are allowed.', 'danger')
                return redirect(request.url)
            
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            if not is_valid_pdf(file_path):
                os.remove(file_path)
                flash(f"Invalid PDF file: {filename}.", 'danger')
                return redirect(request.url)
            
            valid_files.append(file_path)
            log_file_history(current_user.username, filename, file_path, "upload")

        try:
            processed_filename = None
            file_count = len(valid_files)
            
            if file_count == 1:
                # Single file compression
                original_name = os.path.splitext(os.path.basename(valid_files[0]))[0]
                processed_filename = f"{original_name}_compressed.pdf"
                output_path = os.path.join(app.config['COMPRESSED_FOLDER'], processed_filename)
                ghostscript_compress(valid_files[0], output_path)
                log_file_history(current_user.username, processed_filename, output_path, "compress")
            else:
                # Merge and compress using Ghostscript for better performance
                original_name = os.path.splitext(os.path.basename(valid_files[0]))[0]
                processed_filename = f"{original_name}-merged.pdf"
                output_path = os.path.join(app.config['COMBINED_FOLDER'], processed_filename)
                
                # Ghostscript command for merging and compression
                gs_executable = r"C:\\Program Files\\gs\\gs10.04.0\\bin\\gswin64c.exe"
                gs_command = [
                    gs_executable,
                    "-sDEVICE=pdfwrite",
                    "-dCompatibilityLevel=1.4",
                    "-dPDFSETTINGS=/ebook",
                    "-dNOPAUSE",
                    "-dQUIET",
                    "-dBATCH",
                    f"-sOutputFile={output_path}"
                ] + valid_files
                
                logging.debug("Running Ghostscript merge command: " + " ".join(gs_command))
                subprocess.run(gs_command, check=True)
                log_file_history(current_user.username, processed_filename, output_path, "merge")

            # Cleanup and redirect
            for f in valid_files:
                os.remove(f)
            return redirect(url_for('download', filename=processed_filename))

        except subprocess.CalledProcessError as e:
            logging.error(f"Ghostscript processing failed: {e}")
            flash("Error processing PDF files.", "danger")
            return redirect(request.url)
        except Exception as e:
            logging.error(f"Error processing files: {e}", exc_info=True)
            flash('Error processing files.', 'danger')
            return redirect(request.url)
    
    return render_template('upload.html')

def is_valid_pdf(file_path):
    try:
        with open(file_path, 'rb') as f:
            reader = PdfReader(f)
            if len(reader.pages) > 0:
                return True
    except Exception as e:
        logging.error(f"Invalid PDF: {file_path}, Error: {e}")
    return False

@app.route('/download/<filename>')
@login_required
def download(filename):
    if '-merged' in filename:
        folder = app.config['COMBINED_FOLDER']
    elif '_compressed' in filename:
        folder = app.config['COMPRESSED_FOLDER']
    else:
        folder = BASE_PROCESSED_FOLDER
    return send_from_directory(folder, filename, as_attachment=True)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)