from flask import Flask, request, jsonify, send_from_directory
import os
from docx import Document
import requests

app = Flask(__name__, static_folder='../frontend', static_url_path='')

UPLOAD_FOLDER = '../reports'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/check', methods=['POST'])
def check_report():
    if 'report' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['report']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    client_name = request.form.get('clientName')
    start_date = request.form.get('startDate')
    end_date = request.form.get('endDate')

    if not all([client_name, start_date, end_date]):
        return jsonify({'error': 'Missing required fields'}), 400

    # Save file
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

    # Extract text
    try:
        doc = Document(file_path)
        text = '\n'.join([para.text for para in doc.paragraphs])
    except Exception as e:
        return jsonify({'error': f'Error extracting text: {str(e)}'}), 500

    # Build prompt
    prompt = f"""You are an expert IT auditor conducting a stringent review of a SOC report. Your task is to meticulously verify the following:

1. Client Name: The report must consistently refer to the client as "{client_name}". Check every mention and report any variations, omissions, or inconsistencies.

2. Audit Period: The audit period must be exactly from "{start_date}" to "{end_date}". Verify all date references in the report match this period precisely. Report any discrepancies, such as wrong dates, missing dates, or inconsistent formatting.

Report Text:
{text}

Provide a detailed, objective analysis:
- Confirm if the client name matches exactly.
- Confirm if the audit period dates are correct and consistent.
- Highlight any errors, inconsistencies, or areas of concern.
- Be extremely thorough and do not overlook any details."""

    # Call Ollama
    try:
        response = requests.post('http://localhost:11434/api/generate', json={
            'model': 'llama2',  # Adjust model as needed
            'prompt': prompt,
            'stream': False,
            'options': {'temperature': 0.0}  # For deterministic, stringent checking
        })
        response.raise_for_status()
        result = response.json()['response']
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Error calling Ollama: {str(e)}'}), 500

    return jsonify({'result': result})

if __name__ == '__main__':
    app.run(debug=True)