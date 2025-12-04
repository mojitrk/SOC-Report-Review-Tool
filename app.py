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
            prompt = f"""You are validating audit period dates in a SOC report. Search the ENTIRE document for all date mentions.

Your task:
1. Find EVERY place where audit period dates are mentioned
2. Check if they all match the expected dates (semantically)
3. Dates can be in different formats but must mean the same thing:
   - "January 1, 2025" = "1 Jan 2025" = "Jan 1, 2025" (all acceptable)
   - "June 30" = "30 June" = "30th of June" (all acceptable)
4. List ALL locations where dates appear
5. If ANY location has different dates, report the inconsistency

Expected Dates: "{expected_value}"

Document Content:
{document_text[:15000]}

Provide a clear explanation that helps the user understand:
- What dates you found in the document
- Where you found them (list all locations)
- Whether they match the expected dates
- If there are any inconsistencies between different parts of the document

Respond with a JSON object:
{{
  "passed": true/false,
  "reason": "Clear explanation of what dates were found and whether they all match expectations",
  "locations": [
    "Section/Location: dates found",
    "Another location: dates found"
  ]
}}

JSON response:"""
        else:
            # Special handling for report type to be more explicit
            if 'report_type' in input_key.lower() or 'classification' in rule['name'].lower():
                prompt = f"""You are validating a SOC report type. Your task is to find what type of report this actually is, then compare it to what was expected.

STEP 1 - EXTRACT: Look at the document and find where it states the report type:
- Check the TITLE (first line of the document)
- Check any headers mentioning "SOC"
- The document will explicitly say "SOC 1" or "SOC 2" and "Type I" or "Type II" or "Type 2"

STEP 2 - COMPARE: Compare what you found with the expected value.
- Expected: "{expected_value}"
- If they match, PASS
- If they don't match, FAIL

STEP 3 - EXPLAIN: Write a clear explanation for the user:
- State what type you found in the document
- State whether it matches the expected type
- List all locations where you verified this

Document Content:
{document_text[:15000]}

Respond with a JSON object:
{{
  "passed": true/false,
  "reason": "This report is a [type found]. Expected: [expected type]. [Match/Mismatch explanation]",
  "locations": [
    "Title/Header: [exact text showing report type]",
    "Other mentions: [list other places]"
  ]
}}

JSON response:"""
            else:
                prompt = f"""You are a SOC report validator. Search the ENTIRE document and find ALL places where this information appears.

Your task:
1. Find EVERY mention of this information in the document
2. Check if ALL mentions match the expected value: "{expected_value}"
3. For names: Must match exactly (spelling, capitalization)
4. List all locations checked
5. Explain clearly to the user what you found

Rule: {rule['name']}

Expected Value: "{expected_value}"

Document Content:
{document_text[:15000]}

Provide a clear explanation that helps the user understand:
- What you found in the document
- Where you found it (list all locations)
- Whether it matches their expectation
- If there are any inconsistencies

Respond with a JSON object:
{{
  "passed": true/false,
  "reason": "Clear explanation of what was found and whether it matches",
  "locations": [
    "Section/Location: value found",
    "Another location: value found"
  ]
}}

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
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif result_text.startswith('```'):
            lines = result_text.split('\n')
            result_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else result_text
            result_text = result_text.replace('```', '').strip()
        
        # Try to extract JSON from the response
        start = result_text.find('{')
        end = result_text.rfind('}') + 1
        if start != -1 and end > start:
            result_text = result_text[start:end]
        else:
            raise ValueError(f"No valid JSON found in response")
        
        # Clean up common JSON formatting issues
        result_text = result_text.replace('\n', ' ').replace('\r', '').replace('\t', ' ')
        # Remove any text after the closing brace
        if '}' in result_text:
            result_text = result_text[:result_text.rfind('}')+1]
        
        result = json.loads(result_text)
        
        # Handle both single location and locations array for backward compatibility
        locations = result.get('locations', [])
        if not locations and 'location' in result:
            locations = [result['location']]
        
        return {
            'passed': result.get('passed', False),
            'reason': result.get('reason', 'No reason provided'),
            'locations': locations
        }
    except json.JSONDecodeError as e:
        return {
            'passed': False,
            'reason': f'Unable to parse validation result. Please try again.',
            'locations': ['Error occurred during validation']
        }
    except Exception as e:
        return {
            'passed': False,
            'reason': f'Error during validation: {str(e)}',
            'locations': ['Validation error']
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
                'locations': rule_result.get('locations', [])
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
