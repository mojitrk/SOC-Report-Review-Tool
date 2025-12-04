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
        
        # Determine if this is a date-related rule for semantic matching
        is_date_rule = 'audit_period' in input_key.lower() or 'date' in rule['name'].lower()
        
        if is_date_rule:
            prompt = f"""You are a SOC report validator. Extract date information and verify it semantically matches the expected value.

IMPORTANT INSTRUCTIONS FOR DATES:
1. Find the EXACT text snippet from the document containing the dates
2. Dates with the same MEANING should PASS even if formatted differently
3. Examples of equivalent dates: "30 Jun", "30th June", "June 30", "30th of June" - all mean June 30
4. "January 1, 2025", "1 Jan 2025", "1st January 2025" - all mean January 1, 2025
5. The year, month, and day must match semantically, not character-by-character
6. Extract the LOCATION in the document where you found this information (page number, section, or first few words of the paragraph)

Rule: {rule['name']}
Task: {rule['description']}

Expected Value: "{expected_value}"

Document Content:
{document_text[:10000]}

You MUST respond with ONLY a valid JSON object in this exact format:
{{"passed": true, "reason": "Found: [exact text]. Semantically matches expected.", "location": "Found in: [describe where in document]"}} 
OR
{{"passed": false, "reason": "Found: [exact text]. Does not match expected: [expected value].", "location": "Found in: [describe where in document]"}}

JSON response:"""
        else:
            prompt = f"""You are a strict SOC report validator. Extract specific information and verify it matches the expected value.

IMPORTANT INSTRUCTIONS:
1. Find the EXACT text from the document that relates to this rule
2. For names: Must match exactly (spelling, capitalization, punctuation)
3. For report types: Look at the TITLE PAGE and HEADER - the report explicitly states what type it is (SOC 1/SOC 2, Type I/Type II)
4. Extract the LOCATION where you found this information (section name, or first few words nearby)

Rule: {rule['name']}
Task: {rule['description']}

Expected Value: "{expected_value}"

Document Content:
{document_text[:10000]}

You MUST respond with ONLY a valid JSON object in this exact format:
{{"passed": true, "reason": "Found: [exact text from document]. Matches expected.", "location": "Found in: [describe where in document]"}} 
OR
{{"passed": false, "reason": "Found: [exact text from document]. Does not match expected.", "location": "Found in: [describe where in document]"}}

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
            'reason': result.get('reason', 'No reason provided'),
            'location': result.get('location', 'Location not specified')
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
                'reason': rule_result['reason'],
                'location': rule_result.get('location', '')
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
