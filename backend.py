#!/usr/bin/env python3
"""
Backend service for SOC Report Review Tool
Handles report upload, parsing, checklist validation, and LLM-based analysis
"""

import json
import os
import re
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from docx import Document
import PyPDF2
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load checklist configuration
with open("checklist_config.json", "r") as f:
    CHECKLIST_CONFIG = json.load(f)

# LLM Configuration - Using Ollama with local model
LLM_BASE_URL = "http://localhost:11434"  # Ollama default port
LLM_MODEL = "mistral"  # Using Mistral 7B - free, no API key needed

class ReportProcessor:
    """Handles report parsing and text extraction"""
    
    @staticmethod
    def extract_text_from_docx(file_path):
        """Extract text from DOCX file"""
        doc = Document(file_path)
        full_text = "\n".join([para.text for para in doc.paragraphs])
        return full_text
    
    @staticmethod
    def extract_text_from_pdf(file_path):
        """Extract text from PDF file"""
        full_text = ""
        try:
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    full_text += page.extract_text() + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        return full_text
    
    @staticmethod
    def extract_text(file_path):
        """Extract text from uploaded file (DOCX or PDF)"""
        if file_path.lower().endswith(".docx"):
            return ReportProcessor.extract_text_from_docx(file_path)
        elif file_path.lower().endswith(".pdf"):
            return ReportProcessor.extract_text_from_pdf(file_path)
        return ""

class ChecklistValidator:
    """Validates report against checklist rules"""
    
    @staticmethod
    def validate_exact_match(text, rule):
        """Validate exact match rules"""
        expected = rule.get("expected_value", "")
        pattern = rule.get("search_pattern", "")
        
        match = re.search(pattern, text, re.IGNORECASE)
        passed = match is not None
        
        found_value = match.group(0) if match else "Not found"
        
        return {
            "passed": passed,
            "found_value": found_value,
            "explanation": rule["explanation_template"].format(found_value=found_value)
        }
    
    @staticmethod
    def validate_keyword(text, rule):
        """Validate keyword presence rules"""
        keywords = rule.get("keywords", [])
        required_count = rule.get("required_count", 1)
        
        found_keywords = []
        found_count = 0
        
        for keyword in keywords:
            count = len(re.findall(re.escape(keyword), text, re.IGNORECASE))
            if count > 0:
                found_keywords.append(keyword)
                found_count += count
        
        passed = len(found_keywords) >= required_count
        
        return {
            "passed": passed,
            "found_keywords": ", ".join(found_keywords) if found_keywords else "None",
            "found_count": found_count,
            "explanation": rule["explanation_template"].format(
                found_count=found_count,
                found_keywords=", ".join(found_keywords) if found_keywords else "None"
            )
        }
    
    @staticmethod
    def validate_section_header(text, rule):
        """Validate section header presence"""
        section_name = rule.get("section_name", "")
        # Look for the section header (variations of heading formats)
        pattern = rf"^{re.escape(section_name)}|#{re.escape(section_name)}|\*{re.escape(section_name)}\*"
        found = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        
        passed = found is not None
        
        return {
            "passed": passed,
            "explanation": rule["explanation_template"]
        }
    
    @staticmethod
    def validate_negative_keyword(text, rule):
        """Validate that certain keywords are NOT present"""
        keywords = rule.get("keywords", [])
        required_count = rule.get("required_count", 0)  # Should be 0
        
        found_count = 0
        for keyword in keywords:
            count = len(re.findall(re.escape(keyword), text, re.IGNORECASE))
            found_count += count
        
        passed = found_count <= required_count
        
        return {
            "passed": passed,
            "found_count": found_count,
            "explanation": rule["explanation_template"].format(found_count=found_count)
        }
    
    @staticmethod
    def validate_all_rules(report_text):
        """Run all validation rules against report"""
        results = []
        
        for rule in CHECKLIST_CONFIG["rules"]:
            rule_id = rule["rule_id"]
            check_type = rule.get("check_type", "keyword")
            
            # Log progress
            print(f"[VALIDATING] Rule: {rule['rule_name']}")
            
            if check_type == "exact_match":
                result = ChecklistValidator.validate_exact_match(report_text, rule)
            elif check_type == "keyword":
                result = ChecklistValidator.validate_keyword(report_text, rule)
            elif check_type == "section_header":
                result = ChecklistValidator.validate_section_header(report_text, rule)
            elif check_type == "negative_keyword":
                result = ChecklistValidator.validate_negative_keyword(report_text, rule)
            else:
                result = {"passed": False, "explanation": "Unknown check type"}
            
            results.append({
                "rule_id": rule_id,
                "rule_name": rule["rule_name"],
                "severity": rule["severity"],
                "passed": result["passed"],
                "explanation": result["explanation"]
            })
        
        return results

class LLMAnalyzer:
    """Uses LLM to provide enhanced explanations and analysis"""
    
    @staticmethod
    def call_llm(prompt):
        """Call local Ollama LLM"""
        try:
            url = f"{LLM_BASE_URL}/api/generate"
            payload = {
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.3  # Lower temperature for consistency
            }
            
            response = requests.post(url, json=payload, timeout=60)
            
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            else:
                print(f"LLM Error: {response.status_code}")
                return None
        except Exception as e:
            print(f"LLM Connection Error: {e}")
            return None
    
    @staticmethod
    def enhance_rule_explanation(rule, validation_result, report_excerpt=None):
        """Use LLM to enhance explanation for a failed rule"""
        
        # For now, return the basic explanation
        # LLM can be used here later for more sophisticated analysis
        return validation_result["explanation"]

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "service": "SOC Report Review Tool",
        "llm_available": check_llm_availability()
    })

def check_llm_availability():
    """Check if LLM service is available"""
    try:
        response = requests.get(f"{LLM_BASE_URL}/api/tags", timeout=5)
        return response.status_code == 200
    except:
        return False

@app.route("/upload", methods=["POST"])
def upload_report():
    """Upload and process a SOC report"""
    
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files["file"]
    
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    
    if not (file.filename.lower().endswith(".docx") or file.filename.lower().endswith(".pdf")):
        return jsonify({"error": "Only DOCX and PDF files are supported"}), 400
    
    # Save uploaded file
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    
    # Extract text
    print(f"[PROCESSING] Extracting text from {file.filename}")
    report_text = ReportProcessor.extract_text(file_path)
    
    if not report_text:
        os.remove(file_path)
        return jsonify({"error": "Failed to extract text from file"}), 400
    
    # Validate against checklist
    print("[VALIDATING] Running checklist validation...")
    validation_results = ChecklistValidator.validate_all_rules(report_text)
    
    # Calculate summary
    total_rules = len(validation_results)
    passed_rules = sum(1 for r in validation_results if r["passed"])
    critical_failures = [r for r in validation_results if not r["passed"] and r["severity"] == "critical"]
    
    print(f"[COMPLETE] Validation complete: {passed_rules}/{total_rules} passed")
    
    return jsonify({
        "success": True,
        "filename": file.filename,
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_rules": total_rules,
            "passed_rules": passed_rules,
            "failed_rules": total_rules - passed_rules,
            "critical_failures": len(critical_failures),
            "overall_status": "PASS" if len(critical_failures) == 0 else "FAIL"
        },
        "validation_results": validation_results,
        "report_text_preview": report_text[:500] + "..." if len(report_text) > 500 else report_text
    })

@app.route("/checklist", methods=["GET"])
def get_checklist():
    """Get current checklist configuration"""
    return jsonify(CHECKLIST_CONFIG)

if __name__ == "__main__":
    print("Starting SOC Report Review Tool Backend...")
    print(f"LLM Service: {LLM_BASE_URL}")
    print(f"LLM Model: {LLM_MODEL}")
    print(f"Checklist Rules Loaded: {len(CHECKLIST_CONFIG['rules'])}")
    
    # Check LLM availability
    if check_llm_availability():
        print("✓ LLM service is available")
    else:
        print("⚠ LLM service not available at http://localhost:11434")
        print("  Start Ollama or the LLM service to enable AI explanations")
    
    app.run(debug=True, host="0.0.0.0", port=5000)
