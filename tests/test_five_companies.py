"""
Run five-company enrichment test.

  cd ~/company-enrichment
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  PYTHONPATH=src python -m pytest tests/test_five_companies.py -v

Live mode (requires keys in .env):
  MOCK_LLM=false MOCK_SEARCH=false OPENAI_API_KEY=... TAVILY_API_KEY=... \\
    PYTHONPATH=src python -m pytest tests/test_five_companies.py -v
"""

import json
from pathlib import Path
from typing import List

import pytest

from company_enrichment.config import DATA_DIR, OUTPUT_DIR
from company_enrichment.enricher import enrich_many
from company_enrichment.models import CompanyInput
from company_enrichment.scraper import extract_facts_from_html

TEST_FILE = DATA_DIR / "test_companies.json"


@pytest.fixture
def companies() -> List[CompanyInput]:
    raw = json.loads(TEST_FILE.read_text(encoding="utf-8"))
    return [CompanyInput(**row) for row in raw]


@pytest.mark.asyncio
async def test_enrich_five_companies(companies: List[CompanyInput]):
    assert len(companies) == 5
    ids = {c.cpyId for c in companies}
    assert ids == {2151, 2114, 2087, 2065, 2182}

    results = await enrich_many(companies, max_workers=3)
    assert len(results) == 5

    for record in results:
        assert record.company_name
        assert record.cpyId in ids
        assert record.main_url
        assert record.stock_symbol
        assert record.employees
        assert record.company_description
        assert record.wordle_text
        assert record.upload_logo
        assert record.upload_logo.endswith(".jpg")
        assert Path(record.upload_logo).exists()

        out_file = OUTPUT_DIR / f"{record.cpyId}.json"
        assert out_file.exists(), f"missing output for {record.cpyId}"

        saved = json.loads(out_file.read_text(encoding="utf-8"))
        assert saved["record"]["cpyId"] == record.cpyId
        assert saved["record"]["field_sources"]


@pytest.mark.parametrize(
    "name,expected_ticker",
    [
        ("Danaher Corporation", "DHR"),
        ("Ford Motor Company", "F"),
        ("Merck & Co.", "MRK"),
        ("Netflix", "NFLX"),
        ("Kraft Heinz Company", "KHC"),
    ],
)
def test_fixture_tickers(name: str, expected_ticker: str):
    """Mock fixtures include expected tickers for smoke checks."""
    from company_enrichment.llm import _MOCK_FIXTURES

    assert _MOCK_FIXTURES[name.lower()]["stock_symbol"] == expected_ticker


def test_extract_facts_from_realistic_html():
    html = """
    <html>
      <head>
        <meta property="og:image" content="/images/company-campus.jpg">
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Organization",
            "url": "https://example.com",
            "telephone": "+1 212 555 0100",
            "slogan": "Better data for teams",
            "mission": "Help teams validate company information with confidence.",
            "logo": "/assets/logo.png",
            "sameAs": ["https://www.linkedin.com/company/example-company"],
            "address": {
              "@type": "PostalAddress",
              "streetAddress": "123 Market Street",
              "addressLocality": "New York",
              "addressRegion": "NY",
              "postalCode": "10001",
              "addressCountry": "United States"
            }
          }
        </script>
      </head>
      <body>
        <img alt="Example Company logo" src="/brand/logo.png">
        <a href="/careers">Careers</a>
        <a href="/faq">FAQ</a>
        <a href="https://twitter.com/example">Twitter</a>
      </body>
    </html>
    """

    fields, logo_url, image_url = extract_facts_from_html(
        html,
        page_url="https://example.com/about",
        main_url="https://example.com",
    )

    assert fields["phone"] == "+1 212 555 0100"
    assert fields["address_line_1"] == "123 Market Street"
    assert fields["address_line_2"] == "New York, NY, 10001"
    assert fields["country"] == "United States"
    assert fields["career_url"] == "https://example.com/careers"
    assert fields["faq_url"] == "https://example.com/faq"
    assert fields["linkedin_url"] == "https://www.linkedin.com/company/example-company"
    assert fields["twitter_url"] == "https://twitter.com/example"
    assert fields["slogan"] == "Better data for teams"
    assert fields["mission"] == "Help teams validate company information with confidence."
    assert logo_url == "https://example.com/assets/logo.png"
    assert image_url == "https://example.com/images/company-campus.jpg"
