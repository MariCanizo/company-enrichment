# Company Enrichment

Python pipeline for enriching company records with structured profile data, short narrative descriptions, social links, and image assets. The project is designed to run safely in mock mode for local testing, then switch to live search and LLM enrichment when API keys are available.

## What This Project Does

The pipeline starts with a minimal company input:

```json
{
  "cpyId": 2151,
  "company_name": "Danaher Corporation"
}
```

For each company, it attempts to produce a richer record containing:

- Company name and official website
- Logo path and company image path
- Company description and word-cloud text
- Address, country, phone, ticker, employee count, slogan, and mission where available
- Career and FAQ URLs
- LinkedIn, Facebook, Twitter/X, Instagram, and YouTube URLs

Each enriched record is written as a JSON file under `output/`.

## Current Test Dataset

The repository includes a five-company fixture in `data/test_companies.json`:

- Danaher Corporation, `cpyId` 2151
- Ford Motor Company, `cpyId` 2114
- Merck & Co., `cpyId` 2087
- Netflix, `cpyId` 2065
- Kraft Heinz Company, `cpyId` 2182

These are used by the smoke tests and by the default CLI run.

## Pipeline Overview

The main orchestration lives in `src/company_enrichment/enricher.py`.

1. Discover the company's likely official website.
2. Scrape the homepage and common company pages such as contact, about, careers, and investors.
3. Extract social media URLs from scraped page text.
4. Ask the LLM to produce structured enrichment fields.
5. Ask the LLM to generate a company description and word-cloud text.
6. Download or generate logo and company image assets as JPG files.
7. Sanitize text for ISO-8859-1 compatibility and validate image/file constraints.
8. Persist one JSON output file per company.

## Project Structure

```text
company-enrichment/
├── data/
│   └── test_companies.json
├── src/company_enrichment/
│   ├── config.py        # Environment variables and project paths
│   ├── enricher.py      # Main enrichment orchestration
│   ├── images.py        # Image download, resize, and mock placeholders
│   ├── llm.py           # OpenAI and mock enrichment logic
│   ├── models.py        # Pydantic input/output schemas
│   ├── scraper.py       # Web scraping and social-link extraction
│   ├── search.py        # Website discovery and Tavily integration hook
│   ├── validate.py      # Field sanitization and validation
│   └── workers.py       # Batch CLI entrypoint
├── tests/
│   └── test_five_companies.py
├── .env.example
├── requirements.txt
└── run_test.py
```

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local environment file:

```bash
cp .env.example .env
```

The default `.env.example` is configured for offline testing:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
TAVILY_API_KEY=
MOCK_LLM=true
MOCK_SEARCH=true
MAX_WORKERS=3
OUTPUT_DIR=./output
```

## Run the Demo

The fastest way to run the included five-company enrichment is:

```bash
python run_test.py
```

This reads `data/test_companies.json`, enriches the five sample companies, prints a short summary table, and writes output files under `output/`.

## Run the Tests

```bash
PYTHONPATH=src python -m pytest tests/test_five_companies.py -v
```

The tests verify that:

- The five fixture companies load correctly.
- Each company produces an enriched result.
- Required fields such as `company_name`, `main_url`, `stock_symbol`, `employees`, `company_description`, `wordle_text`, and `upload_logo` are populated.
- Logo files are saved as `.jpg`.
- One JSON output file is written per `cpyId`.

## Batch Usage

You can also run the batch worker directly:

```bash
PYTHONPATH=src python -m company_enrichment.workers --file data/test_companies.json --workers 3
```

The input file should be a JSON array with this shape:

```json
[
  {
    "cpyId": 2151,
    "company_name": "Danaher Corporation"
  }
]
```

## Mock Mode vs Live Mode

Mock mode is enabled by default so the project can run without external API keys. In mock mode:

- `search.py` uses seeded official domains for the five fixture companies.
- `llm.py` uses local fixture data instead of calling OpenAI.
- `images.py` creates local placeholder JPG files instead of downloading remote images.

To run live enrichment, update `.env`:

```env
MOCK_LLM=false
MOCK_SEARCH=false
OPENAI_API_KEY=your_openai_key
TAVILY_API_KEY=your_tavily_key
```

Then install the optional search dependency:

```bash
pip install tavily-python
```

Live mode uses Tavily for website discovery and OpenAI for structured and narrative enrichment.

## Output Format

Each output file is written to:

```text
output/{cpyId}.json
```

Example shape:

```json
{
  "enriched_at": "2026-05-25T08:00:00+00:00",
  "validation_errors": [],
  "record": {
    "cpyId": 2151,
    "company_name": "Danaher Corporation",
    "upload_logo": "output/images/2151/logo.jpg",
    "company_description": "...",
    "stock_symbol": "DHR",
    "employees": "63000",
    "main_url": "https://www.danaher.com",
    "wordle_text": "...",
    "company_image": "output/images/2151/company.jpg"
  }
}
```

The full export schema is defined in `CompanyRecord` in `src/company_enrichment/models.py`.

## Notes for the Team

- The current project is a working pipeline sketch with a reliable offline test path.
- Mock mode is useful for demos, CI smoke tests, and development without paid API calls.
- Live mode should be reviewed with real company samples before treating outputs as production-ready.
- The LLM prompts are intentionally conservative: they ask the model to use only provided text and avoid inventing unsupported company details.
- `output/` and `.env` are ignored by Git so generated data and secrets are not committed.

