"""
Batch worker entry point.

Example:
  PYTHONPATH=src python -m company_enrichment.workers --file data/test_companies.json
  PYTHONPATH=src python -m company_enrichment.workers --sql "SELECT cpyId, company_name FROM companies WHERE status='pending' LIMIT 100"
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .config import DATA_DIR, MAX_WORKERS
from .enricher import enrich_many
from .models import CompanyInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_from_json(path: Path) -> list:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [CompanyInput(**r) for r in rows]


async def run_batch(companies: list, workers: int) -> None:
    logger.info("Enriching %s companies with %s workers", len(companies), workers)
    results = await enrich_many(companies, max_workers=workers)
    logger.info("Done. %s records written.", len(results))


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch company enrichment")
    parser.add_argument("--file", type=Path, default=DATA_DIR / "test_companies.json")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    companies = load_from_json(args.file)
    asyncio.run(run_batch(companies, args.workers))


if __name__ == "__main__":
    main()
