import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import httpx

from .config import MOCK_SEARCH, OUTPUT_DIR
from .images import download_and_save_jpg, placeholder_jpg
from .llm import enrich_narrative, enrich_structured
from .models import CompanyInput, CompanyRecord
from .scraper import build_scrape_bundle, extract_social_links
from .validate import sanitize_iso8859_1, validate_record

logger = logging.getLogger(__name__)


async def enrich_company(company: CompanyInput) -> CompanyRecord:
    bundle = await build_scrape_bundle(company)
    structured = await enrich_structured(bundle)
    structured = _merge_scraped_fields(structured, bundle)
    socials = extract_social_links(bundle.pages.values())
    for key, value in socials.items():
        if value and not structured.get(key):
            structured[key] = value
            bundle.field_sources[key] = "scraped page text"

    description, wordle = await enrich_narrative(structured)
    structured["company_description"] = description
    structured["wordle_text"] = wordle
    structured["cpyId"] = company.cpyId
    structured["field_sources"] = bundle.field_sources

    record = CompanyRecord(**structured)
    record = _sanitize_record(record)
    record = await _attach_images(record, bundle)

    errors = validate_record(record)
    if errors:
        logger.warning("Validation issues for cpyId=%s: %s", company.cpyId, errors)

    _persist(record, errors)
    return record


def _merge_scraped_fields(structured: dict, bundle) -> dict:
    merged = dict(structured)
    for key, value in bundle.extracted_fields.items():
        if value and not merged.get(key):
            merged[key] = value
    if bundle.main_url and not merged.get("main_url"):
        merged["main_url"] = bundle.main_url
        bundle.field_sources["main_url"] = "search discovery"
    return merged


def _sanitize_record(record: CompanyRecord) -> CompanyRecord:
    data = record.model_dump()
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = sanitize_iso8859_1(value)
    return CompanyRecord(**data)


async def _attach_images(record: CompanyRecord, bundle) -> CompanyRecord:
    img_dir = OUTPUT_DIR / "images" / str(record.cpyId)

    if MOCK_SEARCH:
        logo_path = placeholder_jpg(record.cpyId, "logo", 250, 250)
        image_path = placeholder_jpg(record.cpyId, "company", 500, 350)
        record.upload_logo = logo_path
        record.company_image = image_path
        return record

    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "CompanyEnrichmentBot/0.1"},
    ) as client:
        logo = await _download_first_valid_image(
            bundle.candidate_logo_urls or [bundle.candidate_logo_url],
            img_dir / "logo.jpg",
            250,
            250,
            client,
        )
        if not logo:
            logo = await _download_first_valid_image(
                bundle.candidate_image_urls or [bundle.candidate_image_url],
                img_dir / "logo.jpg",
                250,
                250,
                client,
            )
        image = await _download_first_valid_image(
            bundle.candidate_image_urls or [bundle.candidate_image_url],
            img_dir / "company.jpg",
            500,
            350,
            client,
        )
    record.upload_logo = logo
    record.company_image = image
    return record


async def _download_first_valid_image(
    candidates: Iterable[Optional[str]],
    dest: Path,
    max_width: int,
    max_height: int,
    client: httpx.AsyncClient,
) -> Optional[str]:
    for url in candidates:
        if not url:
            continue
        path = await download_and_save_jpg(url, dest, max_width, max_height, client)
        if path:
            return path
    return None


def _persist(record: CompanyRecord, errors: List[str]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "validation_errors": errors,
        "record": record.model_dump(),
    }
    path = OUTPUT_DIR / f"{record.cpyId}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def enrich_many(
    companies: List[CompanyInput],
    max_workers: int = 3,
) -> List[CompanyRecord]:
    sem = asyncio.Semaphore(max_workers)

    async def _run(c: CompanyInput) -> CompanyRecord:
        async with sem:
            return await enrich_company(c)

    return await asyncio.gather(*[_run(c) for c in companies])
