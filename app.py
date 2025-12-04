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

IMPORTANT: ONLY check sections that actually contain audit period dates. Skip sections with no dates.

Your task:
1. Find EVERY place where audit period dates are ACTUALLY mentioned (skip sections without dates)
2. For EACH location with dates, extract the EXACT TEXT snippet containing the dates
3. Check if dates match the expected dates (semantically):
   - "January 1, 2025" = "1 Jan 2025" = "Jan 1, 2025" (all acceptable)
   - "June 30" = "30 June" = "30th of June" (all acceptable)
4. Look for ANY conflicting or inconsistent dates throughout the document
5. If MOST locations match but 1-2 have issues, return "partial"
6. If dates are completely wrong or many conflicts exist, return "failed"

Expected Dates: "{expected_value}"

Document Content:
{document_text[:20000]}

Determine the status:
- "passed": ALL date mentions match expected dates perfectly, no conflicts
- "partial": MOST mentions match, but found 1-2 inconsistencies or questionable dates  
- "failed": Many conflicts OR dates don't match expected at all

Respond with a JSON object:
{{
  "passed": "passed"/"partial"/"failed",
  "reason": "Checked X locations with dates. Found: [summary]. [X match, Y conflicts]",
  "locations": [
    "Section Name: 'exact date text from document'",
    "Another Section: 'exact date text from document'"
  ]
}}

JSON response:"""
        else:
            # Special handling for report type to be more explicit
            if 'report_type' in input_key.lower() or 'classification' in rule['name'].lower():
                prompt = f"""You are validating a SOC report type. Search the ENTIRE document for ALL mentions of the report type.

STEP 1 - EXTRACT ALL: Find EVERY place where report type is mentioned:
- Title/Header (first lines of document)
- Body text mentioning "SOC 1" or "SOC 2"
- Any mention of "Type I", "Type II", "Type 1", or "Type 2"
- Extract the EXACT TEXT for each mention

STEP 2 - CHECK FOR CONFLICTS: 
- Do all mentions agree on the same report type?
- Are there any conflicting references (e.g., title says SOC 2 but body mentions SOC 1)?
- CRITICAL: Even ONE mention of wrong type is a conflict that should cause failure!

STEP 3 - DETERMINE STATUS: 
- Expected: "{expected_value}"
- If ALL mentions match expected and ZERO conflicts: "passed"
- If ANY conflicting mention found (even 1): "partial" or "failed"
- If primary type is wrong: "failed"

Document Content:
{document_text[:20000]}

Be strict about conflicts. If you find ANY mention of a different SOC type or Type level, report it.

Respond with a JSON object:
{{
  "passed": "passed"/"partial"/"failed",
  "reason": "Primary type: [type]. Expected: [expected]. Found X mentions. [If conflicts: CONFLICT: found mention of [conflicting type]]",
  "locations": [
    "Title/Header: 'exact text snippet'",
    "Section: 'exact text snippet'",
    "CONFLICT at [location]: 'exact text showing wrong type' (if any)"
  ]
}}

JSON response:"""
            else:
                # Special handling for report specificity - use reasoning
                if 'specificity' in input_key.lower() or 'specificity' in rule['name'].lower():
                    # Extract service org name from user inputs to exclude it from checks
                    service_org = user_inputs.get('service_org_name', '')
                    prompt = f"""You are analyzing whether a SOC report is generic or user-entity specific.

User expects: "{expected_value}"

IMPORTANT: The service organization being audited is "{service_org}". DO NOT count this as the user entity.
Only look for OTHER organizations (clients/customers) mentioned in the report.

Analyze the document to determine specificity:

Generic Report indicators:
- Addressed "To Whom It May Concern" or "To Users of [Service Org] Services"
- No specific client/customer organization named (other than the service org itself)
- Intended for broad distribution to multiple potential clients
- Language like "users of this report" or "user entities" (plural)

User-Entity Specific indicators:
- Addressed to a specific client/customer company (NOT the service org)
- References a particular client by name (e.g., "prepared for ABC Corp")
- Mentions a specific user entity organization that is the customer
- Custom scope for a specific client mentioned

Document Content:
{document_text[:20000]}

Provide reasoning about what type it is and whether it matches expectation.
List any client/customer organizations found (excluding the service org).

Respond with a JSON object:
{{
  "passed": "passed"/"partial"/"failed",
  "reason": "Based on [evidence], this appears to be a [generic/user-specific] report. [Found client org names or no specific client]. [Match/mismatch explanation]",
  "locations": [
    "Evidence: 'exact text snippet showing addressing or client references'"
  ]
}}

JSON response:"""
                else:
                    prompt = f"""You are a SOC report validator. Search the ENTIRE document thoroughly and find ALL places where this information appears.

Your task:
1. Scan the COMPLETE document - don't stop after finding just one occurrence
2. Find EVERY single mention of this information (look in headers, body, footers, titles, sections)
3. For EACH location, extract the EXACT TEXT snippet showing the information
4. Check if ALL mentions match the expected value: "{expected_value}"
5. For names: Must match exactly (spelling, capitalization, punctuation)
6. Look for ANY conflicting information (e.g., different names, spellings, or values)
7. List ALL locations found

Rule: {rule['name']}

Expected Value: "{expected_value}"

Document Content:
{document_text[:20000]}

Determine the status:
- "passed": ALL mentions match expected value perfectly, no conflicts
- "partial": MOST mentions match (75%+), but found 1-2 inconsistencies or conflicts
- "failed": Many conflicts (25%+) OR value doesn't match expected at all

Respond with a JSON object:
{{
  "passed": "passed"/"partial"/"failed",
  "reason": "Found X total mentions. [X match exactly, Y have conflicts/differences]. [Brief explanation]",
  "locations": [
    "Section/Location Name: 'exact text snippet from document'",
    "Another Location: 'exact text snippet from document'",
    "Yet Another Location: 'exact text snippet from document'"
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
        
        # Handle passed field which can be boolean or string ("passed", "partial", "failed")
        passed_value = result.get('passed', False)
        if isinstance(passed_value, str):
            # Normalize the string value
            passed_status = passed_value.lower().strip()
            if passed_status not in ['passed', 'partial', 'failed']:
                # If it's not a valid status string, treat as boolean
                passed_status = "passed" if passed_value.lower() in ['true', 'yes'] else "failed"
        elif passed_value is True:
            passed_status = "passed"
        elif passed_value is False:
            passed_status = "failed"
        else:
            passed_status = "failed"
        
        return {
            'passed': passed_status,
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
        passed_rules = sum(1 for r in results if r['passed'] == 'passed')
        partial_rules = sum(1 for r in results if r['passed'] == 'partial')
        failed_rules = sum(1 for r in results if r['passed'] == 'failed')
        
        return jsonify({
            'success': True,
            'summary': {
                'total': total_rules,
                'passed': passed_rules,
                'partial': partial_rules,
                'failed': failed_rules
            },
            'results': results
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
