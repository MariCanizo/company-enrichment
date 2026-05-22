import logging
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from .config import OUTPUT_DIR, USER_AGENT

logger = logging.getLogger(__name__)


async def download_and_save_jpg(
    url: Optional[str],
    dest: Path,
    max_width: int,
    max_height: int,
    client: httpx.AsyncClient,
) -> Optional[str]:
    if not url:
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        img = img.convert("RGB")
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        img.save(dest, format="JPEG", quality=85)
        return str(dest)
    except Exception as exc:
        logger.warning("Image download/resize failed for %s: %s", url, exc)
        return None


def placeholder_jpg(cpy_id: int, label: str, max_width: int, max_height: int) -> str:
    """Offline test helper when remote image fetch is blocked."""
    out_dir = OUTPUT_DIR / "images" / str(cpy_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{label}.jpg"
    img = Image.new("RGB", (max_width, max_height), color=(240, 240, 240))
    img.save(path, format="JPEG")
    return str(path)
