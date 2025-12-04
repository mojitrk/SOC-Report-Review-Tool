#!/usr/bin/env python3
"""
SOC Report Validator
Validates a SOC report against a checklist of rules
"""

import json
import re
import sys
from pathlib import Path
from docx import Document
import PyPDF2


class ReportValidator:
    """Main validator class"""
    
    def __init__(self, checklist_path):
        """Load checklist config"""
        with open(checklist_path, 'r') as f:
            self.checklist = json.load(f)
        self.results = []
    
    def extract_text_from_docx(self, file_path):
        """Extract all text from DOCX file"""
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    
    def extract_text_from_pdf(self, file_path):
        """Extract all text from PDF file"""
        text = ""
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
        return text
    
    def extract_text(self, file_path):
        """Extract text from DOCX or PDF"""
        if file_path.lower().endswith('.docx'):
            return self.extract_text_from_docx(file_path)
        elif file_path.lower().endswith('.pdf'):
            return self.extract_text_from_pdf(file_path)
        else:
            raise ValueError("Only .docx and .pdf files are supported")
    
    def check_keyword(self, text, rule):
        """Check if keywords are present"""
        keywords = rule.get('keywords', [])
        min_occurrences = rule.get('min_occurrences', 1)
        
        found_count = 0
        for keyword in keywords:
            count = len(re.findall(re.escape(keyword), text, re.IGNORECASE))
            found_count += count
        
        passed = found_count >= min_occurrences
        return passed
    
    def check_section(self, text, rule):
        """Check if section header exists"""
        section_name = rule.get('section_name', '')
        # Look for section header (case-insensitive, start of line)
        pattern = rf'^\s*{re.escape(section_name)}'
        found = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return found is not None
    
    def check_exact_match(self, text, rule):
        """Check if exact pattern matches"""
        pattern = rule.get('pattern', '')
        if not pattern:
            return False
        found = re.search(pattern, text, re.IGNORECASE)
        return found is not None
    
    def validate(self, file_path):
        """Run validation against all rules"""
        print(f"\n{'='*70}")
        print(f"VALIDATING: {Path(file_path).name}")
        print(f"{'='*70}\n")
        
        # Extract text from report
        print("[1/2] Extracting text from report...")
        try:
            report_text = self.extract_text(file_path)
            print(f"      ✓ Extracted {len(report_text)} characters\n")
        except Exception as e:
            print(f"      ✗ Error: {e}")
            return None
        
        # Run validation rules
        print("[2/2] Running validation rules...\n")
        
        critical_failures = 0
        high_failures = 0
        passed_rules = 0
        
        for rule in self.checklist['rules']:
            rule_id = rule['rule_id']
            rule_name = rule['rule_name']
            check_type = rule['check_type']
            severity = rule['severity']
            
            # Run appropriate check
            if check_type == 'keyword':
                passed = self.check_keyword(report_text, rule)
            elif check_type == 'section':
                passed = self.check_section(report_text, rule)
            elif check_type == 'exact_match':
                passed = self.check_exact_match(report_text, rule)
            else:
                passed = False
            
            # Store result
            self.results.append({
                'rule_id': rule_id,
                'rule_name': rule_name,
                'severity': severity,
                'passed': passed
            })
            
            # Print result
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}  [{severity.upper()}] {rule_name}")
            if not passed:
                print(f"         └─ {rule['explanation']}")
                if severity == 'critical':
                    critical_failures += 1
                elif severity == 'high':
                    high_failures += 1
            else:
                passed_rules += 1
        
        # Summary
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"Total Rules:        {len(self.results)}")
        print(f"Passed:             {passed_rules}")
        print(f"Failed:             {len(self.results) - passed_rules}")
        print(f"Critical Failures:  {critical_failures}")
        print(f"High Failures:      {high_failures}")
        
        if critical_failures == 0:
            print(f"\nOVERALL STATUS: ✓ PASS (No critical issues)")
        else:
            print(f"\nOVERALL STATUS: ✗ FAIL ({critical_failures} critical issue(s))")
        
        print(f"{'='*70}\n")
        
        return {
            'passed': critical_failures == 0,
            'critical_failures': critical_failures,
            'high_failures': high_failures,
            'passed_rules': passed_rules,
            'total_rules': len(self.results),
            'results': self.results
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: python validator.py <report_file> [checklist_file]")
        print("Example: python validator.py report.docx checklist.json")
        sys.exit(1)
    
    report_file = sys.argv[1]
    checklist_file = sys.argv[2] if len(sys.argv) > 2 else 'checklist.json'
    
    # Check files exist
    if not Path(report_file).exists():
        print(f"Error: Report file not found: {report_file}")
        sys.exit(1)
    
    if not Path(checklist_file).exists():
        print(f"Error: Checklist file not found: {checklist_file}")
        sys.exit(1)
    
    # Run validator
    validator = ReportValidator(checklist_file)
    result = validator.validate(report_file)
    
    # Exit with appropriate code
    sys.exit(0 if result and result['passed'] else 1)


if __name__ == '__main__':
    main()
