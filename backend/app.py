from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import requests
from docx import Document
import tempfile
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# File upload configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'docx', 'txt'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_docx(file_path):
    """Extract text from a Word document (.docx)"""
    try:
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        raise ValueError(f"Error reading Word document: {str(e)}")

def extract_text_from_file(file_path, filename):
    """Extract text from uploaded file based on file type"""
    if filename.lower().endswith('.docx'):
        return extract_text_from_docx(file_path)
    elif filename.lower().endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        raise ValueError("Unsupported file type")

# Load SOC checklist rules
with open('soc_checklist_rules.json', 'r') as f:
    CHECKLIST_RULES = json.load(f)

# Ollama configuration
OLLAMA_API_URL = os.getenv('OLLAMA_API_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama2')


def check_rule_with_llm(rule, report_text):
    """
    Use Llama via Ollama to check if a rule is satisfied in the report.
    Returns: {'satisfied': bool, 'confidence': float, 'reasoning': str}
    """
    try:
        prompt = f"""You are an SOC audit expert. Analyze the following report to check if this rule is satisfied.

Rule: {rule['name']}
Description: {rule['description']}

Report Text:
{report_text}

Based on the report, is this rule satisfied? 
Respond in JSON format:
{{
  "satisfied": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}

Only respond with the JSON, no other text."""

        response = requests.post(
            f'{OLLAMA_API_URL}/api/generate',
            json={
                'model': OLLAMA_MODEL,
                'prompt': prompt,
                'stream': False
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            response_text = result.get('response', '{}').strip()
            
            # Parse JSON from response
            try:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                    return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Fallback: simple keyword matching
        return check_rule_with_keywords(rule, report_text)

    except requests.exceptions.ConnectionError:
        print("Warning: Could not connect to Ollama. Using keyword matching fallback.")
        return check_rule_with_keywords(rule, report_text)
    except Exception as e:
        print(f"Error with LLM: {str(e)}")
        return check_rule_with_keywords(rule, report_text)


def check_rule_with_keywords(rule, report_text):
    """
    Fallback: Simple keyword matching to check if a rule is satisfied.
    """
    report_lower = report_text.lower()
    keywords = rule.get('keywords', [])
    
    matched_keywords = [kw for kw in keywords if kw.lower() in report_lower]
    match_count = len(matched_keywords)
    total_keywords = len(keywords)
    
    if total_keywords == 0:
        satisfied = False
        confidence = 0.0
    else:
        confidence = match_count / total_keywords
        satisfied = confidence >= 0.3  # Threshold: 30% of keywords matched
    
    return {
        'satisfied': satisfied,
        'confidence': confidence,
        'reasoning': f"Matched {match_count}/{total_keywords} keywords: {', '.join(matched_keywords[:3])}"
    }


@app.route('/api/review', methods=['POST'])
def review_report():
    """
    Main endpoint: Review a SOC report against the checklist rules.
    """
    data = request.json
    report_text = data.get('report_text', '')

    if not report_text.strip():
        return jsonify({'error': 'Report text is required'}), 400

    results = []
    for rule in CHECKLIST_RULES['rules']:
        check_result = check_rule_with_llm(rule, report_text)
        results.append({
            'rule_id': rule['id'],
            'rule_name': rule['name'],
            'importance': rule['importance'],
            'satisfied': check_result['satisfied'],
            'confidence': check_result['confidence'],
            'reasoning': check_result['reasoning']
        })

    # Calculate overall compliance
    total_rules = len(results)
    satisfied_count = sum(1 for r in results if r['satisfied'])
    compliance_score = (satisfied_count / total_rules * 100) if total_rules > 0 else 0

    return jsonify({
        'compliance_score': round(compliance_score, 2),
        'total_rules': total_rules,
        'satisfied_rules': satisfied_count,
        'results': results
    })


@app.route('/api/upload', methods=['POST'])
def upload_report():
    """
    File upload endpoint: Accept Word documents and review them.
    """
    # Check if file is in request
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': f'Only {", ".join(ALLOWED_EXTENSIONS)} files are allowed'}), 400

    try:
        # Save file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)

        # Extract text from file
        report_text = extract_text_from_file(temp_path, file.filename)

        # Clean up temp file
        try:
            os.remove(temp_path)
        except:
            pass

        if not report_text.strip():
            return jsonify({'error': 'File is empty or could not be read'}), 400

        # Review the report
        results = []
        for rule in CHECKLIST_RULES['rules']:
            check_result = check_rule_with_llm(rule, report_text)
            results.append({
                'rule_id': rule['id'],
                'rule_name': rule['name'],
                'importance': rule['importance'],
                'satisfied': check_result['satisfied'],
                'confidence': check_result['confidence'],
                'reasoning': check_result['reasoning']
            })

        # Calculate overall compliance
        total_rules = len(results)
        satisfied_count = sum(1 for r in results if r['satisfied'])
        compliance_score = (satisfied_count / total_rules * 100) if total_rules > 0 else 0

        return jsonify({
            'filename': file.filename,
            'compliance_score': round(compliance_score, 2),
            'total_rules': total_rules,
            'satisfied_rules': satisfied_count,
            'results': results
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


@app.route('/api/rules', methods=['GET'])
def get_rules():
    """Get all available rules."""
    return jsonify(CHECKLIST_RULES)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
