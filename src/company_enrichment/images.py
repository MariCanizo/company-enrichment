import logging
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageStat

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
        img = _image_from_response(url, resp)
        img = img.convert("RGB")
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        if _is_low_information_image(img):
            logger.warning("Image rejected as blank or too small: %s", url)
            return None
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
    seed = (cpy_id * 37 + sum(ord(ch) for ch in label)) % 120
    bg = (70 + seed, 95 + (seed // 2), 150 + (seed // 3))
    img = Image.new("RGB", (max_width, max_height), color=bg)
    draw = ImageDraw.Draw(img)
    text = f"MOCK {label.upper()}\n{cpy_id}"
    draw.text((16, max_height // 2 - 16), text, fill=(255, 255, 255))
    img.save(path, format="JPEG")
    return str(path)


def _image_from_response(url: str, resp: httpx.Response) -> Image.Image:
    content_type = resp.headers.get("content-type", "").lower()
    suffix = Path(urlparse(url).path).suffix.lower()
    if "svg" in content_type or suffix == ".svg":
        try:
            import cairosvg
        except ImportError as exc:
            raise RuntimeError("Install cairosvg to convert SVG logos to JPG") from exc

        png_bytes = cairosvg.svg2png(bytestring=resp.content)
        return Image.open(BytesIO(png_bytes))

    return Image.open(BytesIO(resp.content))


def _is_low_information_image(img: Image.Image) -> bool:
    if img.width < 24 or img.height < 24:
        return True
    grayscale = img.convert("L")
    extrema = grayscale.getextrema()
    stat = ImageStat.Stat(grayscale)
    return (extrema[1] - extrema[0]) < 5 or stat.var[0] < 4
