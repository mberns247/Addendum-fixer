# Addendum Fixer

A web application for processing and merging PDF order forms and addendums.

## Features

- **PDF Processing**: Merges new order forms with existing agreements/addendums
- **Interactive Preview**: Single-page view with navigation controls
- **Professional File Naming**: Automatically formats filenames with company name and date
- **Secure File Handling**: Session-based temporary file management with automatic cleanup

## Setup

1. Clone the repository:
```bash
git clone https://github.com/[your-username]/Addendum-Fixer.git
cd Addendum-Fixer
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:8000`

## Usage

1. Upload your existing order form (with addendum)
2. Upload the new order form
3. Preview the merged document
4. Download the processed PDF with the standardized filename

## File Naming Convention

Downloaded files follow the format:
`Order Form and Addendum - [Company Name] - Trustpilot (YYYY.MM.DD)`

- Company name is automatically extracted from the order form
- Date is automatically set to the current date
- Falls back to "Unknown Company" if company name cannot be found
