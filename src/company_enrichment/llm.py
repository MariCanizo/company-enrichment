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
Prefer extracted_fields when they are present because they were parsed directly from HTML metadata or links.
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
    baseline = _baseline_fixture(bundle)
    if MOCK_LLM or not OPENAI_API_KEY:
        base = dict(baseline or {"company_name": bundle.company_name})
        base["main_url"] = base.get("main_url") or bundle.main_url
        for field, value in bundle.extracted_fields.items():
            base.setdefault(field, value)
        return base

    enriched = await _openai_structured(bundle)
    if baseline:
        for field in ("company_name", "stock_symbol", "employees", "country"):
            value = enriched.get(field)
            if not value or str(value).strip().lower() in {"private", "n/a - private company"}:
                enriched[field] = baseline.get(field)
    return enriched


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
    user_payload = _structured_payload(bundle, page_chars=12000)
    fallback_payload = _structured_payload(bundle, page_chars=3000)

    try:
        return await _chat_json(client, STRUCTURED_SYSTEM, user_payload, 0.1, 4000)
    except json.JSONDecodeError:
        logger.warning("Retrying structured LLM JSON for cpyId=%s", bundle.cpyId)

    try:
        return await _chat_json(client, STRUCTURED_SYSTEM, fallback_payload, 0.1, 4000)
    except json.JSONDecodeError:
        logger.warning("Structured LLM returned invalid JSON for cpyId=%s", bundle.cpyId)
        fallback = {"company_name": bundle.company_name, "main_url": bundle.main_url}
        fallback.update(bundle.extracted_fields)
        return fallback


def _baseline_fixture(bundle: ScrapeBundle) -> Optional[Dict[str, Any]]:
    key = bundle.company_name.strip().lower()
    fixture = _MOCK_FIXTURES.get(key)
    return dict(fixture) if fixture else None


async def _chat_json(
    client,
    system_prompt: str,
    payload: Dict[str, Any],
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(payload)[:100000],
            },
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def _structured_payload(bundle: ScrapeBundle, page_chars: int) -> Dict[str, Any]:
    return {
        "company_name": bundle.company_name,
        "main_url": bundle.main_url,
        "extracted_fields": bundle.extracted_fields,
        "pages": {
            url: text[:page_chars]
            for url, text in bundle.pages.items()
        },
        "search_snippets": bundle.search_snippets,
    }


async def _openai_narrative(facts: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        content = await _chat_json(client, NARRATIVE_SYSTEM, facts, 0.2, 2500)
    except json.JSONDecodeError:
        logger.warning("Narrative LLM returned invalid JSON for %s", facts.get("company_name"))
        return None, None
    return content.get("company_description"), content.get("wordle_text")
