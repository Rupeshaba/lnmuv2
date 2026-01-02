from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Optional
import os
from pathlib import Path

from logic.logic import (
    free_search, get_distinct_years, get_distinct_colleges, get_distinct_courses,
    get_distinct_subjects, get_students_paginated, get_student_details_by_rollno
)
from schemas.schemas import SearchResult, Student, PaginatedResults
from report_generator import generate_report
from config.config import TEMP_REPORTS_DIR, DB_PATH
from database.database import DOWNLOAD_STATUS

app = FastAPI(
    title="LNMU Search API",
    description="API for searching student data and generating reports",
    version="1.0.0",
)

@app.get("/status", summary="Get database download status")
async def get_db_status():
    return DOWNLOAD_STATUS

@app.get("/search", response_model=List[SearchResult], summary="Free text search for students")
async def search_students(q: str, limit: int = 20):
    """Perform a free text search across multiple student fields."""
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' cannot be empty")
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Database not ready. Please wait for download to complete.")
    return free_search(q, limit)

@app.get("/years", response_model=List[int], summary="Get distinct academic years")
async def get_years():
    """Retrieve a list of distinct academic years available in the database."""
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Database not ready. Please wait for download to complete.")
    return get_distinct_years()

@app.get("/colleges", response_model=List[str], summary="Get distinct colleges for a given year")
async def get_colleges(year: Optional[int] = None):
    """Retrieve a list of distinct colleges, optionally filtered by academic year."""
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Database not ready. Please wait for download to complete.")
    return get_distinct_colleges(year)

@app.get("/courses", response_model=List[str], summary="Get distinct courses for a given year and college")
async def get_courses(year: Optional[int] = None, college: Optional[str] = None):
    """Retrieve a list of distinct courses, optionally filtered by academic year and college."""
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Database not ready. Please wait for download to complete.")
    return get_distinct_courses(year, college)

@app.get("/subjects", response_model=List[str], summary="Get distinct subjects for given year, college, and course")
async def get_subjects(year: Optional[int] = None, college: Optional[str] = None, course: Optional[str] = None):
    """Retrieve a list of distinct subjects, optionally filtered by academic year, college, and course."""
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Database not ready. Please wait for download to complete.")
    return get_distinct_subjects(year, college, course)

@app.get("/students", response_model=PaginatedResults, summary="Get paginated list of students")
async def get_students(
    year: Optional[int] = None,
    college: Optional[str] = None,
    course: Optional[str] = None,
    subject: Optional[str] = None,
    page: int = 1,
    page_size: int = 10
):
    """Retrieve a paginated list of students, with optional filters."""
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Database not ready. Please wait for download to complete.")
    return get_students_paginated(year, college, course, subject, page, page_size)

@app.get("/student/{rollno}", response_model=Student, summary="Get full details of a student by roll number")
async def get_student_details(rollno: str):
    """Retrieve full details of a single student using their roll number."""
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Database not ready. Please wait for download to complete.")
    student = get_student_details_by_rollno(rollno)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student

@app.get("/report/{rollno}", summary="Generate and download a student report")
async def get_student_report(rollno: str, background_tasks: BackgroundTasks):
    """Generate a student report as an image and return it for download."""
    if not Path(DB_PATH).exists():
        raise HTTPException(status_code=503, detail="Database not ready. Please wait for download to complete.")
    student_data = get_student_details_by_rollno(rollno)
    if not student_data:
        raise HTTPException(status_code=404, detail="Student not found")
    
    output_filename = f"{rollno}_report.jpg"
    report_path = generate_report(student_data.dict(), output_filename)

    if not report_path or not report_path.exists():
        raise HTTPException(status_code=500, detail="Failed to generate report.")
    
    def cleanup_file():
        if report_path.exists():
            os.remove(report_path)

    background_tasks.add_task(cleanup_file)
    return FileResponse(report_path, media_type="image/jpeg", filename=output_filename)
