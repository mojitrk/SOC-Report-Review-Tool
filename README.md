# SOC Report Review Tool - MVP

A simple, functional MVP for auditing SOC reports against a checklist of compliance rules using a local Llama LLM.

## Project Overview

This tool helps KPMG IT auditors quickly review SOC reports for compliance with key audit checklist items such as:
- Audit period clarity
- Client entity name verification
- Management responsibility statements
- Scope of work definition
- Testing procedures documentation
- Control exception documentation
- Auditor sign-off
- Conclusion/opinion provided

## Architecture

```
SOC-Report-Review-Tool/
├── backend/
│   ├── app.py                    # Flask API server
│   ├── soc_checklist_rules.json  # Audit checklist rules
│   └── requirements.txt          # Python dependencies
├── frontend/
│   └── index.html                # Simple web UI
└── README.md
```

## Setup & Installation

### Prerequisites

1. **Python 3.8+** - For the backend
2. **Ollama** - For running Llama locally
   - Download from: https://ollama.ai
   - Pull a model: `ollama pull llama2` (or `ollama pull neural-chat` for faster performance on weak hardware)

### Backend Setup

1. Install Python dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Start Ollama (in a separate terminal):
```bash
ollama serve
# In another terminal, ensure model is available:
ollama pull llama2
```

3. Run the Flask backend:
```bash
python app.py
```

The API will be available at `http://localhost:5000`

### Frontend Setup

1. Open `frontend/index.html` in a web browser, or serve it:
```bash
cd frontend
python -m http.server 8000
# Then visit http://localhost:8000
```

## Usage

1. Paste a SOC report into the text area
2. Click "Review Report"
3. The tool will analyze the report against all checklist rules
4. View results with compliance score, individual rule status, and confidence levels

## API Endpoints

### POST `/api/review`
Reviews a SOC report against the checklist rules.

**Request:**
```json
{
  "report_text": "full SOC report text here..."
}
```

**Response:**
```json
{
  "compliance_score": 87.5,
  "total_rules": 8,
  "satisfied_rules": 7,
  "results": [
    {
      "rule_id": "rule_001",
      "rule_name": "Audit Period Mentioned",
      "importance": "critical",
      "satisfied": true,
      "confidence": 0.95,
      "reasoning": "Report clearly states audit period from January 1 to December 31, 2024"
    }
  ]
}
```

### GET `/api/rules`
Returns all available checklist rules.

### GET `/api/health`
Health check endpoint.

## Features

- ✅ Local LLM processing (no cloud dependencies)
- ✅ 8 SOC audit compliance rules
- ✅ Confidence scoring for each check
- ✅ Fallback keyword matching if LLM unavailable
- ✅ Clean, intuitive web interface
- ✅ Real-time compliance score calculation

## Environment Variables

```bash
OLLAMA_API_URL=http://localhost:11434  # Ollama API URL
OLLAMA_MODEL=llama2                     # Model name to use
```

## Performance Notes

- **Llama 2**: ~5-10 seconds per review (more accurate)
- **Neural Chat**: ~2-3 seconds per review (faster, slightly less accurate)
- Fallback keyword matching: <100ms (used if Ollama unavailable)

## MVP Scope

This is a functional MVP demonstrating:
1. ✅ Backend API with Llama integration
2. ✅ Basic frontend for user interaction
3. ✅ 8 critical SOC audit rules
4. ✅ LLM-based analysis with keyword matching fallback

## Future Enhancements

- [ ] Upload PDF/Word documents directly
- [ ] Store review history and audit trails
- [ ] Advanced rule customization UI
- [ ] Multi-report comparison
- [ ] Detailed findings and remediation tracking
- [ ] Authentication and role-based access
- [ ] Integration with enterprise systems

## Troubleshooting

**Frontend can't connect to backend:**
- Ensure Flask is running on port 5000
- Check CORS is enabled

**LLM analysis is slow:**
- Use a faster model: `ollama pull neural-chat`
- Increase hardware resources

**Ollama connection refused:**
- Ensure Ollama is running: `ollama serve`
- Check URL is correct in `.env` or code

## License

KPMG Internal Use
