from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class CompanyInput(BaseModel):
    cpyId: int
    company_name: str


class CompanyRecord(BaseModel):
    cpyId: int
    company_name: Optional[str] = Field(None, max_length=255)
    upload_logo: Optional[str] = None
    company_description: Optional[str] = Field(None, max_length=1500)
    address_line_1: Optional[str] = Field(None, max_length=255)
    address_line_2: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    stock_symbol: Optional[str] = Field(None, max_length=32)
    employees: Optional[str] = Field(None, max_length=100)
    main_url: Optional[str] = Field(None, max_length=350)
    career_url: Optional[str] = Field(None, max_length=255)
    faq_url: Optional[str] = Field(None, max_length=255)
    slogan: Optional[str] = Field(None, max_length=100)
    mission: Optional[str] = Field(None, max_length=500)
    wordle_text: Optional[str] = Field(None, max_length=3000)
    linkedin_url: Optional[str] = Field(None, max_length=255)
    facebook_url: Optional[str] = Field(None, max_length=255)
    twitter_url: Optional[str] = Field(None, max_length=255)
    instagram_url: Optional[str] = Field(None, max_length=255)
    youtube_url: Optional[str] = Field(None, max_length=255)
    company_image: Optional[str] = None
    field_sources: Dict[str, str] = Field(default_factory=dict)

    @field_validator("stock_symbol")
    @classmethod
    def normalize_private_ticker(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        lowered = v.strip().lower()
        if lowered in ("private", "n/a", "na"):
            return "N/A - private company"
        return v.strip()

    def to_export_dict(self) -> Dict[str, Any]:
        """Flat dict matching your prompt field labels (without cpyId)."""
        return self.model_dump(exclude={"cpyId"})


class ScrapeBundle(BaseModel):
    """Raw text gathered before LLM synthesis."""

    cpyId: int
    company_name: str
    main_url: Optional[str] = None
    pages: Dict[str, str] = Field(default_factory=dict)
    candidate_logo_url: Optional[str] = None
    candidate_image_url: Optional[str] = None
    candidate_logo_urls: List[str] = Field(default_factory=list)
    candidate_image_urls: List[str] = Field(default_factory=list)
    extracted_fields: Dict[str, str] = Field(default_factory=dict)
    field_sources: Dict[str, str] = Field(default_factory=dict)
    search_snippets: List[str] = Field(default_factory=list)
