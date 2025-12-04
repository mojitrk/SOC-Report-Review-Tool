from flask import Flask, request, jsonify, send_from_directory
import os
from docx import Document
import requests
import json
import uuid

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
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], str(uuid.uuid4()) + '_' + file.filename)
    file.save(file_path)

    # Extract text
    try:
        doc = Document(file_path)
        text = '\n'.join([para.text for para in doc.paragraphs])
    except Exception as e:
        return jsonify({'error': f'Error extracting text: {str(e)}'}), 500

    # Load rules and perform checks
    rules = json.load(open('../rules.json'))
    results = []
    for check in rules['checks']:
        desc = check['description']
        check_prompt = check['prompt'].replace('${clientName}', client_name).replace('${startDate}', start_date).replace('${endDate}', end_date)
        full_prompt = f"You are an expert IT auditor. Focus ONLY on this check: {desc}. {check_prompt}\n\nReport Text:\n{text}\n\nProvide a concise analysis for this check only. Confirm if it passes or report discrepancies."
        
        try:
            response = requests.post('http://localhost:11434/api/generate', json={
                'model': 'mistral',
                'prompt': full_prompt,
                'stream': False,
                'options': {'temperature': 0.0}
            })
            response.raise_for_status()
            result = response.json()['response']
            results.append(f"**{check['id'].replace('_', ' ').title()}**: {result}")
        except requests.exceptions.RequestException as e:
            results.append(f"**{check['id'].replace('_', ' ').title()}**: Error calling Ollama: {str(e)}")

    return jsonify({'result': '\n\n'.join(results)})

if __name__ == '__main__':
    app.run(debug=True)