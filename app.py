import os
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import docx
import ollama
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'docx'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_docx(file_path):
    """Extract text from Word document"""
    doc = docx.Document(file_path)
    full_text = []
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            full_text.append(paragraph.text)
    return '\n'.join(full_text)

def load_rules():
    """Load rules from JSON file"""
    with open('rules.json', 'r') as f:
        return json.load(f)

def check_rule_with_llm(rule, document_text):
    """Check a single rule against the document using local LLM"""
    prompt = f"""You are reviewing a SOC report. You need to determine if the following rule is satisfied.

Rule: {rule['name']}
Description: {rule['description']}

Document Content:
{document_text[:8000]}  # Limit to avoid token limits

Based on the document content, does this SOC report satisfy the rule?
Respond with ONLY a JSON object in this exact format:
{{"passed": true/false, "reason": "brief explanation"}}"""

    try:
        response = ollama.chat(model='llama3.2:3b', messages=[
            {
                'role': 'user',
                'content': prompt
            }
        ])
        
        result_text = response['message']['content'].strip()
        
        # Try to extract JSON from the response
        # Sometimes LLMs add extra text, so we look for the JSON object
        start = result_text.find('{')
        end = result_text.rfind('}') + 1
        if start != -1 and end > start:
            result_text = result_text[start:end]
        
        result = json.loads(result_text)
        return {
            'passed': result.get('passed', False),
            'reason': result.get('reason', 'No reason provided')
        }
    except Exception as e:
        return {
            'passed': False,
            'reason': f'Error checking rule: {str(e)}'
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only .docx files are allowed'}), 400
    
    try:
        # Save the file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract text from document
        document_text = extract_text_from_docx(filepath)
        
        # Load rules
        rules = load_rules()
        
        # Check each rule
        results = []
        for rule in rules['rules']:
            rule_result = check_rule_with_llm(rule, document_text)
            results.append({
                'rule_name': rule['name'],
                'description': rule['description'],
                'passed': rule_result['passed'],
                'reason': rule_result['reason']
            })
        
        # Clean up uploaded file
        os.remove(filepath)
        
        # Calculate summary
        total_rules = len(results)
        passed_rules = sum(1 for r in results if r['passed'])
        
        return jsonify({
            'success': True,
            'summary': {
                'total': total_rules,
                'passed': passed_rules,
                'failed': total_rules - passed_rules
            },
            'results': results
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
