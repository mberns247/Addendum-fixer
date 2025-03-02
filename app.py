import os
import re
import uuid
import shutil
from datetime import datetime, timedelta
from io import BytesIO
from flask import Flask, render_template, request, send_file, jsonify, session
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TEMP_FOLDER'] = 'temp'
app.secret_key = os.urandom(24)

def cleanup_old_files():
    """Clean up temporary files older than 1 hour"""
    now = datetime.now()
    temp_dir = app.config['TEMP_FOLDER']
    
    if os.path.exists(temp_dir):
        for session_dir in os.listdir(temp_dir):
            session_path = os.path.join(temp_dir, session_dir)
            if os.path.isdir(session_path):
                dir_time = datetime.fromtimestamp(os.path.getctime(session_path))
                if now - dir_time > timedelta(hours=1):
                    shutil.rmtree(session_path)

def get_session_dir():
    """Get or create a session directory for temporary files"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    session_dir = os.path.join(app.config['TEMP_FOLDER'], session['session_id'])
    os.makedirs(session_dir, exist_ok=True)
    return session_dir

def extract_company_name(pdf_bytes):
    """Extract company name from the first page of the order form."""
    reader = PdfReader(BytesIO(pdf_bytes))
    if len(reader.pages) > 0:
        text = reader.pages[0].extract_text()
        # Look for company name after the label
        match = re.search(r'Company\s*name[:\s]+(.*?)(?:\n|$)', text, re.IGNORECASE)
        if match:
            # Clean up the company name
            company_name = match.group(1).strip()
            # Remove any special characters that might cause issues in filenames
            company_name = re.sub(r'[<>:"/\\|?*]', '', company_name)
            return company_name
    return None

def extract_quote_number(pdf_bytes):
    """Extract quote number (Q######) from PDF content."""
    reader = PdfReader(BytesIO(pdf_bytes))
    for page in reader.pages:
        text = page.extract_text()
        match = re.search(r'Q\d{6}', text)
        if match:
            return match.group(0)
    return None

def find_addendum_start(reader):
    """Find the page where the addendum starts."""
    for i, page in enumerate(reader.pages):
        text = page.extract_text().lower()
        if 'addendum' in text:
            return i
    return None

def process_pdfs(old_pdf_bytes, new_pdf_bytes):
    """Process the PDFs to create the final document."""
    print("\nStarting PDF processing...")
    
    # Extract company name from new order form
    company_name = extract_company_name(new_pdf_bytes)
    if company_name:
        print(f"Found company name: {company_name}")
        # Save company name to temp file
        session_dir = get_session_dir()
        with open(os.path.join(session_dir, 'company_name.txt'), 'w') as f:
            f.write(company_name)
    else:
        print("Could not find company name")
    
    # Create PDF writer for final document
    writer = PdfWriter()
    
    # Load PDFs
    new_reader = PdfReader(BytesIO(new_pdf_bytes))
    old_reader = PdfReader(BytesIO(old_pdf_bytes))
    
    print(f"New PDF has {len(new_reader.pages)} pages")
    print(f"Old PDF has {len(old_reader.pages)} pages")
    
    # Find signature section in old PDF
    signature_page = -1
    order_form_end = -1
    for i, page in enumerate(old_reader.pages):
        text = page.extract_text()
        if "Trustpilot" in text and re.search(r'[A-Za-z0-9\s,]+address', text, re.IGNORECASE):
            signature_page = i
            order_form_end = i + 1  # The page after signature is the last page of old order form
            print(f"Found signature page at index {i}")
            print(f"Old order form ends at index {order_form_end}")
            break
    
    if signature_page == -1:
        raise ValueError("Could not find signature page in old PDF")
    
    # Step 1: Add new order form pages
    print("\nStep 1: Adding new order form pages")
    for i in range(len(new_reader.pages)):
        writer.add_page(new_reader.pages[i])
        print(f"Added new order form page {i+1}")
    
    # Step 2: Add addendum pages, skipping the old order form
    print("\nStep 2: Adding addendum pages")
    for i in range(order_form_end + 1, len(old_reader.pages)):
        writer.add_page(old_reader.pages[i])
        print(f"Added addendum page {i+1}")
    
    print(f"\nFinal document has {len(writer.pages)} pages")
    
    # Save to buffer
    output_buffer = BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    
    return output_buffer

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'oldPdf' not in request.files or 'newPdf' not in request.files:
        return jsonify({'error': 'Both PDFs are required'}), 400
    
    old_pdf = request.files['oldPdf']
    new_pdf = request.files['newPdf']
    
    try:
        # Clean up old files
        cleanup_old_files()
        
        # Get session directory
        session_dir = get_session_dir()
        
        # Extract quote numbers first
        old_pdf_bytes = old_pdf.read()
        new_pdf_bytes = new_pdf.read()
        new_quote = extract_quote_number(new_pdf_bytes)
        
        # Find quote in addendum
        old_reader = PdfReader(BytesIO(old_pdf_bytes))
        addendum_quote = None
        for page in old_reader.pages:
            text = page.extract_text()
            if "ADDENDUM TO QUOTE:" in text:
                quote_match = re.search(r'Q\d{6}', text)
                if quote_match:
                    addendum_quote = quote_match.group(0)
                    break
        
        # Process PDFs
        output_buffer = process_pdfs(old_pdf_bytes, new_pdf_bytes)
        
        # Save processed PDF
        pdf_path = os.path.join(session_dir, 'processed.pdf')
        with open(pdf_path, 'wb') as f:
            f.write(output_buffer.getvalue())
        
        # Convert pages to images for preview
        preview_images = []
        
        # Open the PDF with PyMuPDF for preview
        doc = fitz.open(pdf_path)
        print(f'Converting {len(doc)} pages to preview images')
        
        # Convert each page to an image
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
            preview_path = os.path.join(session_dir, f'preview_{page_num}.jpg')
            pix.save(preview_path)
            preview_images.append(f'/temp/{session["session_id"]}/preview_{page_num}.jpg')
            print(f'Saved preview for page {page_num + 1} of {len(doc)}')
        
        doc.close()
        
        return jsonify({
            'success': True,
            'preview_images': preview_images,
            'new_quote': new_quote,
            'addendum_quote': addendum_quote
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/temp/<session_id>/<path:filename>')
def serve_temp(session_id, filename):
    if 'session_id' not in session or session['session_id'] != session_id:
        return jsonify({'error': 'Invalid session'}), 403
    return send_file(
        os.path.join(app.config['TEMP_FOLDER'], session_id, filename)
    )

@app.route('/download', methods=['GET'])
def download():
    if 'session_id' not in session:
        return jsonify({'error': 'No active session'}), 404
    
    session_dir = os.path.join(app.config['TEMP_FOLDER'], session['session_id'])
    pdf_path = os.path.join(session_dir, 'processed.pdf')
    company_name_path = os.path.join(session_dir, 'company_name.txt')
    
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'No processed PDF found'}), 404
    
    # Get company name from temp file
    company_name = 'Unknown Company'
    if os.path.exists(company_name_path):
        with open(company_name_path, 'r') as f:
            company_name = f.read().strip()
    
    # Format today's date
    today = datetime.now().strftime('%Y.%m.%d')
    
    # Create filename
    filename = f'Order Form and Addendum - {company_name} - Trustpilot ({today}).pdf'
    
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)
    app.run(port=8000, debug=True)
