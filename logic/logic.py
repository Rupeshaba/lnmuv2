import re
import requests
import urllib3
from io import BytesIO
from PIL import Image, ImageOps
from typing import List, Optional

# Suppress SSL warnings for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config.config import TABLES, SEARCH_COLS, IMPORTANT_FIELDS, BASE_URLS, STUDENTS_PER_PAGE
from database.database import execute_query, get_tables
from schemas.schemas import Student, SearchResult, PaginatedResults


# ------------------------------------------------------------
# DATA NORMALIZATION & HELPERS
# ------------------------------------------------------------

def clean_value(val):
    if val is None or str(val).strip().upper() == "NULL" or str(val).strip() == "":
        return ""
    return str(val).strip()

def normalize_name(name):
    return name.title() if name else ""

def format_dob(dob_str):
    if not dob_str: return ""
    match = re.match(r"^(\d{2}[-/]\d{2}[-/]\d{4}).*", dob_str)
    if match:
        return match.group(1).replace("-", "/")
    match_dt = re.match(r"^(\d{4}-\d{2}-\d{2}).*", dob_str)
    if match_dt:
        parts = match_dt.group(1).split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return dob_str.split(" ")[0]

def generate_full_image_url(partial_path, table_name, is_photo=True):
    if not partial_path or clean_value(partial_path) == "":
        return ""

    base_url = BASE_URLS.get(table_name)
    if not base_url:
        return ""

    path = str(partial_path).strip().replace(" ", "%20")

    if path.startswith("http://") or path.startswith("https://"):
        return path

    if path.startswith("/"):
        return base_url.rstrip("/") + path

    return base_url + path

def normalize_student_data(row, table_name):
    if not row: return None

    clean_row = {k: clean_value(row.get(k)) for k in row.keys()}

    if "cname" in clean_row: clean_row["cname"] = normalize_name(clean_row["cname"])
    if "fname" in clean_row: clean_row["fname"] = normalize_name(clean_row["fname"])
    if "mname" in clean_row: clean_row["mname"] = normalize_name(clean_row["mname"])
    if "dob" in clean_row: clean_row["dob"] = format_dob(clean_row["dob"])

    clean_row["table_name"] = table_name
    clean_row["FULL_PHOTO_URL"] = generate_full_image_url(clean_row.get("photo"), table_name, is_photo=True)
    clean_row["FULL_SIGN_URL"] = generate_full_image_url(clean_row.get("sign"), table_name, is_photo=False)

    return Student(**clean_row)

def fetch_binary_content(url):
    try:
        if not url: return None
        headers = {
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36",
            "Accept":
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://google.com",
            "Connection": "keep-alive",
        }
        r = requests.get(url, headers=headers, timeout=20, verify=False, allow_redirects=True)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"[IMG FETCH ERROR] {url}: {e}")
        return None

def safe_open_image(binary):
    if not binary: return None
    try:
        img = Image.open(BytesIO(binary))
        img.verify()
        img = Image.open(BytesIO(binary)).convert("RGBA")
        return img
    except Exception as e:
        print(f"[IMAGE OPEN ERROR] {e}")
        return None


# ------------------------------------------------------------
# SEARCH SYSTEM (FREE SEARCH)
# ------------------------------------------------------------

def detect_input_type(query):
    query = query.strip()
    if re.fullmatch(r"\d{12}", query): return "rollno"
    elif re.fullmatch(r"\d{10}", query): return "mobile"
    elif "@" in query: return "email"
    elif re.fullmatch(r"\d{6}", query): return "c_pincode"
    elif re.fullmatch(r"\d+", query): return "adhaar"
    else: return "text"


def _detect_tables_from_rollno(rollno: str) -> List[str]:
    """
    Rollno ke pehle 2 digits se year detect karo.
    e.g. "234211050007" → year=23 → ["lnmu_ugentrance23"]
    Fallback: saari tables
    """
    if len(rollno) == 12:
        yr = rollno[:2]
        candidate = f"lnmu_ugentrance{yr}"
        if candidate in get_tables():
            return [candidate]
    return get_tables()


def _build_text_search_conditions(col: str) -> str:
    return f"{col} LIKE ?"


def free_search_count(query: str) -> int:
    """Total count of results for a search query (no data fetch)."""
    input_type = detect_input_type(query)
    searchable_text_cols = ["cname", "cadd", "c_city"]
    total = 0
    seen_rollnos = set()

    for table_name in get_tables():
        if input_type == "text":
            for col in searchable_text_cols:
                sql = f"SELECT rollno FROM {table_name} WHERE {col} LIKE ?"
                rows = execute_query(sql, (f"%{query}%",))
                for row in rows:
                    identifier = (row.get("rollno"), table_name)
                    if identifier not in seen_rollnos:
                        seen_rollnos.add(identifier)
                        total += 1
        elif input_type in SEARCH_COLS:
            sql = f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {input_type} = ?"
            result = execute_query(sql, (query,), fetch_one=True)
            if result:
                total += result.get("cnt", 0)

    return total


def free_search(query: str, limit: int = 10, offset: int = 0) -> List[SearchResult]:
    """
    Search across all tables with SQL-level LIMIT/OFFSET pagination.
    For text search: deduplicates by (rollno, table_name).
    """
    input_type = detect_input_type(query)
    results = []
    seen = set()

    searchable_text_cols = ["cname", "cadd", "c_city"]

    for table_name in get_tables():
        if input_type == "text":
            for col in searchable_text_cols:
                # Fetch a reasonable batch to handle deduplication, then slice
                sql = f"SELECT rollno, cname, mobile, adhaar, photo FROM {table_name} WHERE {col} LIKE ? LIMIT 500"
                rows = execute_query(sql, (f"%{query}%",))
                for row in rows:
                    identifier = (row.get("rollno"), table_name)
                    if identifier not in seen:
                        seen.add(identifier)
                        results.append(SearchResult(
                            table_name=table_name,
                            cname=normalize_name(clean_value(row.get("cname"))),
                            rollno=clean_value(row.get("rollno")),
                            mobile=clean_value(row.get("mobile")),
                            adhaar=clean_value(row.get("adhaar")),
                            FULL_PHOTO_URL=generate_full_image_url(row.get("photo"), table_name)
                        ))
        elif input_type in SEARCH_COLS:
            sql = f"SELECT rollno, cname, mobile, adhaar, photo FROM {table_name} WHERE {input_type} = ? LIMIT ? OFFSET ?"
            rows = execute_query(sql, (query, limit, offset))
            for row in rows:
                identifier = (row.get("rollno"), table_name)
                if identifier not in seen:
                    seen.add(identifier)
                    results.append(SearchResult(
                        table_name=table_name,
                        cname=normalize_name(clean_value(row.get("cname"))),
                        rollno=clean_value(row.get("rollno")),
                        mobile=clean_value(row.get("mobile")),
                        adhaar=clean_value(row.get("adhaar")),
                        FULL_PHOTO_URL=generate_full_image_url(row.get("photo"), table_name)
                    ))

    # For exact-column searches, offset is handled in SQL above
    # For text search, we do in-memory slice (dedup needed anyway)
    if input_type == "text":
        return results[offset: offset + limit]

    return results[:limit]


def free_search_paginated(query: str, page: int = 1, page_size: int = 10) -> PaginatedResults:
    """
    Paginated free search.
    - Exact field matches (rollno/mobile/email/adhaar): SQL-level pagination, fast COUNT.
    - Text search (name/address/city): in-memory dedup with bounded 500-row fetch.
    """
    input_type = detect_input_type(query)
    offset = (page - 1) * page_size

    if input_type in SEARCH_COLS:
        # Fast path: exact column match — COUNT from DB, then paginated fetch
        total_items = free_search_count(query)
        items_raw = free_search(query, limit=page_size, offset=offset)
    else:
        # Text search: fetch up to 500 unique results, paginate in memory
        all_results = free_search(query, limit=500, offset=0)
        total_items = len(all_results)
        items_raw = all_results[offset: offset + page_size]

    total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0

    items = [
        {
            "table_name": item.table_name,
            "cname": item.cname,
            "rollno": item.rollno,
            "mobile": item.mobile,
            "adhaar": item.adhaar,
            "FULL_PHOTO_URL": item.FULL_PHOTO_URL
        }
        for item in items_raw
    ]

    return PaginatedResults(
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        page_size=page_size,
        items=items
    )


# ------------------------------------------------------------
# GUIDED DATA APIs
# ------------------------------------------------------------

def get_distinct_years():
    years = sorted([int(re.search(r"\d+", t).group()) for t in get_tables() if re.search(r"\d+", t)])
    return years

def get_distinct_colleges(year: Optional[int] = None) -> List[str]:
    tables_to_search = [f"lnmu_ugentrance{year}"] if year else get_tables()
    colleges = set()
    for table_name in tables_to_search:
        if table_name in get_tables():
            rows = execute_query(
                f"SELECT DISTINCT allotedcollege FROM {table_name} "
                f"WHERE allotedcollege IS NOT NULL AND allotedcollege != '' ORDER BY allotedcollege"
            )
            colleges.update(clean_value(row["allotedcollege"]) for row in rows if clean_value(row["allotedcollege"]) != "")
    return sorted(list(colleges))

def get_distinct_courses(year: Optional[int] = None, college: Optional[str] = None) -> List[str]:
    tables_to_search = [f"lnmu_ugentrance{year}"] if year else get_tables()
    courses = set()
    for table_name in tables_to_search:
        if table_name in get_tables():
            try:
                sql = f"SELECT DISTINCT major FROM {table_name} WHERE major IS NOT NULL AND major != ''"
                params = []
                if college:
                    sql += " AND allotedcollege = ?"
                    params.append(college)
                sql += " ORDER BY major"
                rows = execute_query(sql, params)
                print(f"[DEBUG] Query major field for {table_name}: found {len(rows) if rows else 0} rows")
                if rows:
                    for row in rows:
                        val = clean_value(row.get("major", ""))
                        if val:
                            courses.add(val)
            except Exception as e:
                print(f"[DEBUG] Major field query failed: {e}")

            if not courses:
                sql = f"SELECT DISTINCT allotedhonours FROM {table_name} WHERE allotedhonours IS NOT NULL AND allotedhonours != ''"
                params = []
                if college:
                    sql += " AND allotedcollege = ?"
                    params.append(college)
                sql += " ORDER BY allotedhonours"
                rows = execute_query(sql, params)
                if rows:
                    for row in rows:
                        val = clean_value(row.get("allotedhonours", ""))
                        if val:
                            courses.add(val)

    result = sorted(list(courses))
    print(f"[DEBUG] Final courses list for year {year}, college {college}: {result}")
    return result

def get_distinct_subjects(year: Optional[int] = None, college: Optional[str] = None, course: Optional[str] = None) -> List[str]:
    tables_to_search = [f"lnmu_ugentrance{year}"] if year else get_tables()
    subjects = set()
    for table_name in tables_to_search:
        if table_name in get_tables():
            sql = f"SELECT DISTINCT allotedhonours FROM {table_name} WHERE allotedhonours IS NOT NULL AND allotedhonours != ''"
            params = []
            if college:
                sql += " AND allotedcollege = ?"
                params.append(college)
            if course:
                sql += " AND allotedcourse = ?"
                params.append(course)
            sql += " ORDER BY allotedhonours"
            rows = execute_query(sql, params)
            subjects.update(clean_value(row["allotedhonours"]) for row in rows if clean_value(row["allotedhonours"]) != "")
    return sorted(list(subjects))


def get_students_paginated(
    year: Optional[int] = None,
    college: Optional[str] = None,
    course: Optional[str] = None,
    subject: Optional[str] = None,
    page: int = 1,
    page_size: int = STUDENTS_PER_PAGE
) -> PaginatedResults:
    """
    ✅ OPTIMIZED: Uses SQL COUNT + LIMIT/OFFSET instead of loading all rows into memory.
    Previously fetched ALL students then paginated in Python — now DB does the work.
    """
    tables_to_search = [f"lnmu_ugentrance{year}"] if year else get_tables()

    total_items = 0
    all_students = []
    offset = (page - 1) * page_size

    # When searching across multiple tables we need a combined total first,
    # then fetch only the relevant slice per table.
    table_counts = []
    for table_name in tables_to_search:
        if table_name not in get_tables():
            continue

        sql_conditions = []
        params = []

        if college:
            sql_conditions.append("allotedcollege = ?")
            params.append(college)
        if course:
            sql_conditions.append("allotedcourse = ?")
            params.append(course)
        if subject:
            sql_conditions.append("(major = ? OR allotedhonours = ?)")
            params.append(subject)
            params.append(subject)

        where_clause = " WHERE " + " AND ".join(sql_conditions) if sql_conditions else ""

        count_sql = f"SELECT COUNT(*) as cnt FROM {table_name}{where_clause}"
        result = execute_query(count_sql, params, fetch_one=True)
        cnt = result["cnt"] if result else 0
        table_counts.append((table_name, cnt, params, where_clause))
        total_items += cnt

    # Now figure out which table(s) the requested page falls into
    remaining_offset = offset
    for table_name, cnt, params, where_clause in table_counts:
        if remaining_offset >= cnt:
            # This page starts after this table — skip it
            remaining_offset -= cnt
            continue

        # How many rows to fetch from this table
        rows_needed = min(page_size - len(all_students), cnt - remaining_offset)

        select_sql = (
            f"SELECT * FROM {table_name}{where_clause} "
            f"ORDER BY cname LIMIT ? OFFSET ?"
        )
        rows = execute_query(select_sql, params + [rows_needed, remaining_offset])
        remaining_offset = 0  # Only first matching table needs offset applied

        print(f"[DEBUG] get_students_paginated - Table: {table_name}, "
              f"Filters: college={college}, course={course}, subject={subject}, "
              f"Fetched: {len(rows) if rows else 0} rows (page {page})")

        for row in rows:
            normalized_student = normalize_student_data(row, table_name)
            if normalized_student:
                all_students.append(normalized_student.dict())

        if len(all_students) >= page_size:
            break

    total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0

    return PaginatedResults(
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        page_size=page_size,
        items=all_students
    )


# ------------------------------------------------------------
# STUDENT DETAIL API
# ------------------------------------------------------------

def get_student_details_by_rollno(rollno: str) -> Optional[Student]:
    """
    ✅ OPTIMIZED: Rollno ke pehle 2 digits se year detect karta hai.
    e.g. rollno "234211..." → year 23 → sirf lnmu_ugentrance23 check karo.
    Worst case (unknown format) → saari tables fallback.
    """
    tables_to_check = _detect_tables_from_rollno(rollno)

    for table_name in tables_to_check:
        sql = f"SELECT * FROM {table_name} WHERE rollno = ? LIMIT 1"
        row = execute_query(sql, (rollno,), fetch_one=True)
        if row:
            return normalize_student_data(row, table_name)
    return None
    
