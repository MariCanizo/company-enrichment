import re
from typing import List, Optional

from .models import CompanyRecord

# Characters outside ISO-8859-1 (rough check; excludes control chars except tab/newline)
_NON_ISO8859_1 = re.compile(r"[^\x00-\xFF]")

_SMART_PUNCT = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
    }
)


def sanitize_iso8859_1(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = text.translate(_SMART_PUNCT)
    cleaned = _NON_ISO8859_1.sub("", cleaned)
    return cleaned


def validate_record(record: CompanyRecord) -> List[str]:
    """Return human-readable validation errors."""
    errors: List[str] = []
    data = record.model_dump()

    for key, value in data.items():
        if key == "cpyId" or value is None:
            continue
        if isinstance(value, str):
            if _NON_ISO8859_1.search(value):
                errors.append(f"{key}: contains non ISO-8859-1 characters")

    if record.upload_logo and not record.upload_logo.lower().endswith(".jpg"):
        errors.append("upload_logo: expected .jpg path or URL")
    if record.company_image and not record.company_image.lower().endswith(".jpg"):
        errors.append("company_image: expected .jpg path or URL")

    return errors
