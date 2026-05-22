#!/usr/bin/env python3
"""CLI entry: enrich the five test companies and print a summary table."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from company_enrichment.config import DATA_DIR, MOCK_LLM, MOCK_SEARCH, OUTPUT_DIR
from company_enrichment.enricher import enrich_many
from company_enrichment.models import CompanyInput


async def main() -> None:
    rows = json.loads((DATA_DIR / "test_companies.json").read_text(encoding="utf-8"))
    companies = [CompanyInput(**r) for r in rows]

    print(f"MOCK_LLM={MOCK_LLM} MOCK_SEARCH={MOCK_SEARCH}")
    print(f"Output dir: {OUTPUT_DIR}\n")

    results = await enrich_many(companies, max_workers=3)

    print(f"{'cpyId':<8} {'company_name':<28} {'ticker':<8} {'main_url'}")
    print("-" * 90)
    for r in results:
        print(
            f"{r.cpyId:<8} {(r.company_name or '')[:28]:<28} "
            f"{(r.stock_symbol or '')[:8]:<8} {(r.main_url or '')[:40]}"
        )
    print(f"\nWrote {len(results)} JSON files under {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
