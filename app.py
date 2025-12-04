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

def check_rule_with_llm(rule, document_text, user_inputs=None):
    """Check a single rule against the document using local LLM"""
    
    # Build the prompt based on whether the rule requires user input
    if rule.get('requires_input') and user_inputs:
        input_key = rule.get('input_key')
        expected_value = user_inputs.get(input_key, '')
        
        prompt = f"""You are a strict SOC report validator. Your job is to extract specific information from the report and verify it EXACTLY matches the expected value.

IMPORTANT INSTRUCTIONS:
1. Extract the EXACT text from the document that relates to this rule
2. Compare it character-by-character with the expected value
3. Be EXTREMELY strict - even minor differences mean FAILURE
4. If dates have the same meaning but different format (e.g., "Jan 1" vs "January 1"), that is still a MISMATCH
5. Do NOT be lenient or forgiving - exact match only

Rule: {rule['name']}
Task: {rule['description']}

Expected Value: "{expected_value}"

Document Content:
{document_text[:10000]}

You MUST respond with ONLY a valid JSON object (no markdown, no extra text) in this exact format:
{{"passed": true, "reason": "Found: [exact text from document]. Matches expected value."}} 
OR
{{"passed": false, "reason": "Found: [exact text from document]. Does not match expected: [expected value]."}}

JSON response:"""
    else:
        prompt = f"""You are reviewing a SOC report. You need to determine if the following rule is satisfied.

Rule: {rule['name']}
Description: {rule['description']}

Document Content:
{document_text[:10000]}

Based on the document content, does this SOC report satisfy the rule?
Respond with ONLY a valid JSON object (no markdown, no extra text) in this exact format:
{{"passed": true/false, "reason": "brief explanation"}}

JSON response:"""

    try:
        response = ollama.chat(model='llama3.2', messages=[
            {
                'role': 'user',
                'content': prompt
            }
        ], options={
            'temperature': 0.1  # Lower temperature for more consistent, deterministic outputs
        })
        
        result_text = response['message']['content'].strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith('```'):
            lines = result_text.split('\n')
            result_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else result_text
        
        result_text = result_text.strip()
        
        # Try to extract JSON from the response
        # Sometimes LLMs add extra text, so we look for the JSON object
        start = result_text.find('{')
        end = result_text.rfind('}') + 1
        if start != -1 and end > start:
            result_text = result_text[start:end]
        else:
            raise ValueError(f"No valid JSON found in response: {result_text[:200]}")
        
        # Clean up common JSON formatting issues
        result_text = result_text.replace('\n', ' ').replace('\r', '')
        
        result = json.loads(result_text)
        return {
            'passed': result.get('passed', False),
            'reason': result.get('reason', 'No reason provided')
        }
    except json.JSONDecodeError as e:
        return {
            'passed': False,
            'reason': f'LLM response parsing error. Please try again. (Invalid JSON: {str(e)})'
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
        
        # Get user inputs from form data
        user_inputs = {}
        for key in request.form:
            user_inputs[key] = request.form[key]
        
        # Load rules
        rules = load_rules()
        
        # Check each rule
        results = []
        for rule in rules['rules']:
            rule_result = check_rule_with_llm(rule, document_text, user_inputs)
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
