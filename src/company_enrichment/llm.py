import json
import logging
from typing import Any, Dict, Optional, Tuple

from .config import MOCK_LLM, OPENAI_API_KEY, OPENAI_MODEL
from .models import CompanyRecord, ScrapeBundle

logger = logging.getLogger(__name__)

STRUCTURED_SYSTEM = """You are a company data enrichment analyst.
Use ONLY the provided extracted web text and URLs.
Return JSON matching the schema exactly.
Use null for any field not supported by the provided text.
Do not invent phone numbers, addresses, slogans, missions, or social URLs.
stock_symbol: ticker only (e.g. DHR), or "N/A - private company" if private.
employees: one value only, not a range.
Plain text only, ISO-8859-1 compatible punctuation."""

NARRATIVE_SYSTEM = """Write company_description (max 1500 chars, 4-6 short paragraphs) and wordle_text (max 3000 chars)
using ONLY the JSON facts provided. Do not invent facts. Plain text only."""


_MOCK_FIXTURES: Dict[str, Dict[str, Any]] = {
    "danaher corporation": {
        "company_name": "Danaher Corporation",
        "stock_symbol": "DHR",
        "employees": "63000",
        "country": "United States",
        "main_url": "https://www.danaher.com",
    },
    "ford motor company": {
        "company_name": "Ford Motor Company",
        "stock_symbol": "F",
        "employees": "171000",
        "country": "United States",
        "main_url": "https://www.ford.com",
    },
    "merck & co.": {
        "company_name": "Merck & Co.",
        "stock_symbol": "MRK",
        "employees": "70000",
        "country": "United States",
        "main_url": "https://www.merck.com",
    },
    "netflix": {
        "company_name": "Netflix",
        "stock_symbol": "NFLX",
        "employees": "13000",
        "country": "United States",
        "main_url": "https://www.netflix.com",
    },
    "kraft heinz company": {
        "company_name": "Kraft Heinz Company",
        "stock_symbol": "KHC",
        "employees": "36000",
        "country": "United States",
        "main_url": "https://www.kraftheinzcompany.com",
    },
}


async def enrich_structured(bundle: ScrapeBundle) -> Dict[str, Any]:
    if MOCK_LLM or not OPENAI_API_KEY:
        key = bundle.company_name.strip().lower()
        base = _MOCK_FIXTURES.get(key, {"company_name": bundle.company_name})
        base["main_url"] = base.get("main_url") or bundle.main_url
        return base

    return await _openai_structured(bundle)


async def enrich_narrative(facts: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    if MOCK_LLM or not OPENAI_API_KEY:
        name = facts.get("company_name", "Company")
        desc = (
            f"{name} is a global enterprise referenced in the enrichment pipeline test fixture. "
            f"Headquarters country: {facts.get('country', 'unknown')}. "
            f"Employees (fixture): {facts.get('employees', 'unknown')}. "
            "This description is placeholder text for offline testing."
        )[:1500]
        wordle = f"{desc} {facts.get('slogan') or ''} {facts.get('mission') or ''}"[:3000]
        return desc, wordle

    return await _openai_narrative(facts)


async def _openai_structured(bundle: ScrapeBundle) -> Dict[str, Any]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    user_payload = {
        "company_name": bundle.company_name,
        "main_url": bundle.main_url,
        "pages": bundle.pages,
        "search_snippets": bundle.search_snippets,
    }
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": STRUCTURED_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(user_payload)[:100000],
            },
        ],
        temperature=0.1,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


async def _openai_narrative(facts: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": NARRATIVE_SYSTEM},
            {"role": "user", "content": json.dumps(facts)[:50000]},
        ],
        temperature=0.2,
    )
    content = json.loads(response.choices[0].message.content or "{}")
    return content.get("company_description"), content.get("wordle_text")
