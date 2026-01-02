from pydantic import BaseModel, Field
from typing import Optional, List

class Student(BaseModel):
    table_name: str = Field(..., description="The database table/year the student record belongs to")
    FULL_PHOTO_URL: Optional[str] = Field(None, description="Full URL of the student's photo")
    FULL_SIGN_URL: Optional[str] = Field(None, description="Full URL of the student's signature")
    # Dynamically add all other fields from the database
    # For a full list, refer to IMPORTANT_FIELDS in config.py
    class Config:
        extra = "allow"

class SearchResult(BaseModel):
    table_name: str
    cname: str
    rollno: str
    mobile: Optional[str]
    adhaar: Optional[str]
    FULL_PHOTO_URL: Optional[str]

class PaginatedResults(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    page_size: int
    items: List[dict]

class ReportTemplate(BaseModel):
    layout: dict
    sections: dict
    fonts: dict
    colors: dict
