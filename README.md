# SOC Report Review Tool

A tool for reviewing SOC 1 and SOC 2 reports using LLM-based checks.

## Prerequisites

- Python 3.x installed
- Ollama installed and running locally (download from https://ollama.ai/)
- Pull a model, e.g., `ollama pull llama2`

## Setup and Run

1. Double-click `setup_and_run.bat` to install dependencies and start the server.
   - This will install Python packages and run the Flask app on `http://localhost:5000`.

2. Alternatively, manually:
   - `cd backend`
   - `pip install -r requirements.txt`
   - `python app.py`

3. Open `http://localhost:5000` in your browser.

## Usage

- Enter the expected client name and audit period dates.
- Upload a .docx SOC report.
- Click "Review Report" to get an LLM-based analysis.

## Rules

Checks are defined in `rules.json`. Add or modify checks there to customize the review process.