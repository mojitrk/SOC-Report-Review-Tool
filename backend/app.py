from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import requests

app = Flask(__name__)
CORS(app)

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
