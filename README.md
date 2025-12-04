# SOC Report Review Tool

An AI-powered tool for reviewing SOC (System and Organization Controls) reports against compliance rules using a local LLM.

## Features

- 📄 Upload Word (.docx) SOC reports
- 🤖 Local LLM analysis (no cloud services needed)
- ✅ Automated rule checking without regex
- 📊 Clear pass/fail results with explanations
- 🎨 Modern, intuitive web interface

## Prerequisites

- Python 3.8 or higher
- [Ollama](https://ollama.ai/) installed and running

## Setup Instructions

### 1. Install Ollama

Download and install Ollama from [https://ollama.ai/](https://ollama.ai/)

### 2. Pull the LLM Model

```powershell
ollama pull llama3.2:3b
```

This downloads a small, efficient 3B parameter model (about 2GB). You can use other models by modifying `app.py`.

### 3. Install Python Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Run the Application

```powershell
python app.py
```

The application will start on `http://localhost:5000`

## Usage

1. Open your browser and navigate to `http://localhost:5000`
2. Upload a SOC report (.docx file)
3. Click "Review Report"
4. Wait for the AI analysis to complete
5. Review the results showing which rules passed or failed

## Customizing Rules

Edit `rules.json` to add, remove, or modify compliance rules. Each rule should have:

```json
{
  "name": "Rule Name",
  "description": "Detailed description of what the rule checks for"
}
```

The LLM will analyze the document and determine if each rule is satisfied based on the description.

## How It Works

1. **Upload**: The app accepts Word documents and extracts their text content
2. **Analysis**: Each rule is sent to the local LLM along with the document content
3. **Evaluation**: The LLM determines if the rule is satisfied and provides reasoning
4. **Results**: Clear pass/fail status is displayed with explanations

## Minimal Dependencies

This tool uses only essential packages:
- **Flask**: Lightweight web framework
- **python-docx**: Word document parsing
- **ollama**: Local LLM integration
- **werkzeug**: Secure file handling

No complex NLP libraries, no cloud APIs, no regex patterns needed.

## Why Local LLM?

- **Privacy**: Your documents never leave your machine
- **Cost**: No API fees or rate limits
- **Flexibility**: Easy to swap models and customize behavior
- **Intelligence**: LLMs understand context better than regex patterns

## Troubleshooting

### Ollama not found
Make sure Ollama is installed and running. Test with:
```powershell
ollama list
```

### Model not found
Pull the model first:
```powershell
ollama pull llama3.2:3b
```

### Out of memory
Use a smaller model like `llama3.2:1b` or increase your system memory.

### Slow analysis
- Use a smaller model
- Reduce document size
- Consider using GPU acceleration if available

## License

MIT License - Feel free to use and modify as needed.
