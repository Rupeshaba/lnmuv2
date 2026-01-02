from telegram import (
    InputFile, InlineKeyboardButton, InlineKeyboardMarkup, Update
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)
import re
import os
import math
import asyncio
from telegram import error

from config.config import BOT_TOKEN, TEMP_REPORTS_DIR, STUDENTS_PER_PAGE, IMPORTANT_FIELDS # IMPORTANT_FIELDS added here
from logic.logic import (
    free_search, get_distinct_years, get_distinct_colleges, get_distinct_courses,
    get_distinct_subjects, get_students_paginated, get_student_details_by_rollno,
    fetch_binary_content, safe_open_image
)
from report_generator import generate_report

# State management for guided search (per user)
user_states = {}

class UserState:
    def __init__(self):
        self.year = None
        self.college = None
        self.course = None
        self.subject = None
        self.page = 1
        self.last_students_results = [] # Store full student objects
        self.last_search_query = None # For /search command
        self.years_cache = [] # Cache for years to map indices
        self.colleges_cache = [] # Cache for colleges to map indices
        self.courses_cache = [] # Cache for courses to map indices
        self.subjects_cache = [] # Cache for subjects to map indices
        self.in_free_search = False # Track if user is in free search mode
        self.free_search_results = [] # Store all free search results
        self.free_search_page = 1 # Current page for free search

    def reset(self):
        self.year = None
        self.college = None
        self.course = None
        self.subject = None
        self.page = 1
        self.last_students_results = []
        self.last_search_query = None
        self.years_cache = []
        self.colleges_cache = []
        self.courses_cache = []
        self.subjects_cache = []
        self.in_free_search = False
        self.free_search_results = []
        self.free_search_page = 1

def get_user_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = UserState()
    return user_states[user_id]

# ------------------------------------------------------------
# HELPERS FOR BOT UI
# ------------------------------------------------------------

def build_keyboard(options, callback_prefix, current_page=None, total_pages=None, user_state=None):
    keyboard = []
    for i in range(0, len(options), 2): # 2 options per row
        row = []
        # Use index-based callback data to avoid exceeding 64-byte limit
        row.append(InlineKeyboardButton(options[i], callback_data=f"{callback_prefix}_idx_{i}"))
        if i + 1 < len(options):
            row.append(InlineKeyboardButton(options[i+1], callback_data=f"{callback_prefix}_idx_{i+1}"))
        keyboard.append(row)

    if current_page is not None and total_pages is not None and total_pages > 1:
        nav_row = []
        if current_page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{callback_prefix}_prev_{current_page}"))
        nav_row.append(InlineKeyboardButton(f"Page {current_page}/{total_pages}", callback_data="ignore_page"))
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{callback_prefix}_next_{current_page}"))
        keyboard.append(nav_row)
    
    # Add a back to main menu button for guided search
    if callback_prefix.startswith("college_") or callback_prefix.startswith("course_") or \
       callback_prefix.startswith("subject_") or callback_prefix.startswith("student_list_"):
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="start_guided")])

    return InlineKeyboardMarkup(keyboard)

async def send_paginated_students(update: Update, context: ContextTypes.DEFAULT_TYPE, user_state: UserState):
    results_obj = get_students_paginated(
        year=user_state.year,
        college=user_state.college,
        course=user_state.course,
        subject=user_state.subject,
        page=user_state.page,
        page_size=STUDENTS_PER_PAGE
    )

    user_state.last_students_results = results_obj.items # Store full dicts

    if not results_obj.items:
        text = "No students found for your selection. Please go back to Main Menu and try again."
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=build_keyboard([], "start_guided"))
        else:
            await update.message.reply_text(text, reply_markup=build_keyboard([], "start_guided"))
        return

    # Create a list of (student_name, photo_url) for display
    student_display_info = []
    for student_data_dict in results_obj.items:
        s = get_student_details_by_rollno(student_data_dict.get("rollno")) # Re-fetch to ensure full Student object
        if s:
            student_display_info.append({"name": s.cname, "photo_url": s.FULL_PHOTO_URL, "rollno": s.rollno})

    # Send each student as a separate message with photo and action buttons
    for i, student_info in enumerate(student_display_info):
        caption = f"👤 <b>{student_info["name"]}</b>"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("View Full Details", callback_data=f"view_{student_info["rollno"]}")],
            [InlineKeyboardButton("📄 Generate Report", callback_data=f"report_{student_info["rollno"]}")]
        ])

        if student_info["photo_url"]:
            photo_binary = fetch_binary_content(student_info["photo_url"])
            if photo_binary:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=InputFile(photo_binary, filename=f"{student_info["rollno"]}_photo.jpg"),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=caption + "\n(Photo not available)",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=caption + "\n(Photo not available)",
                parse_mode="HTML",
                reply_markup=keyboard
            )
    
    # Add pagination controls at the end of the student list
    if results_obj.total_pages > 1:
        nav_keyboard = []
        nav_row = []
        if user_state.page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"student_list_prev_{user_state.page}"))
        nav_row.append(InlineKeyboardButton(f"Page {user_state.page}/{results_obj.total_pages}", callback_data="ignore_page"))
        if user_state.page < results_obj.total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"student_list_next_{user_state.page}"))
        nav_keyboard.append(nav_row)
        nav_keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="start_guided")])

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Navigate students:",
            reply_markup=InlineKeyboardMarkup(nav_keyboard)
        )
    else: # If only one page, still offer Main Menu
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="", # Empty text for just buttons
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="start_guided")]])
        )

# ------------------------------------------------------------
# COMMAND HANDLERS
# ------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = UserState() # Reset state on /start
    
    help_text = """
🎓 <b>Welcome to LNMU Student Search Bot!</b>

This bot helps you find and view student information from Lalit Narayan Mithila University.

<b>How to use:</b>

1️⃣ <b>Free Search</b> - Search by Roll No, Mobile, Aadhaar, Email, Pincode, or Name
   Command: Send any search term directly

2️⃣ <b>Guided Search</b> - Search by filtering Year → College → Honours → Student
   Command: /search

<b>Commands:</b>
/start - Show this help message
/search - Start guided search mode

<b>Features:</b>
✅ View student details (Name, DOB, Contact, etc.)
✅ Generate professional student report cards
✅ Search by multiple criteria

Type /search to begin guided search or send any student information to search directly!
    """
    
    await update.message.reply_text(help_text, parse_mode="HTML")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /search command - starts guided search"""
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    user_state.reset() # Reset state for new guided search
    user_state.in_free_search = False # Disable free search mode
    
    years = get_distinct_years()
    if not years:
        await update.message.reply_text("❌ No academic years found in database.")
        return
    
    year_options = [f"{y}-{y+4}" for y in years]
    user_state.years_cache = [y for y in years]
    
    await update.message.reply_text(
        "📚 <b>Guided Search Started</b>\n\n"
        "📍 Step 1 of 4: Select Academic Year\n\n"
        "Please choose an academic year:",
        parse_mode="HTML",
        reply_markup=build_keyboard(year_options, "year", user_state=user_state)
    )

async def free_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)
    user_state.reset() # Reset guided search state
    user_state.in_free_search = True # Set flag to indicate user is in free search mode
    user_state.last_search_query = None # Clear previous free search query
    
    # Handle both message and callback query
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "🔍 <b>Free Search Mode Activated</b>\n\n"
            "Please send me any of the following to search:\n"
            "✅ Roll No\n"
            "✅ Mobile Number\n"
            "✅ Aadhaar Number\n"
            "✅ Email Address\n"
            "✅ Pincode\n"
            "✅ Student Name\n\n"
            "<i>Searching...</i>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            "🔍 <b>Free Search Mode Activated</b>\n\n"
            "Please send me any of the following to search:\n"
            "✅ Roll No\n"
            "✅ Mobile Number\n"
            "✅ Aadhaar Number\n"
            "✅ Email Address\n"
            "✅ Pincode\n"
            "✅ Student Name",
            parse_mode="HTML"
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user_state = get_user_state(user_id)

    # Check if the user is in a free search context
    if not text:
        await update.message.reply_text("Please send a valid message.")
        return
    
    # Auto-enable free search mode if not already enabled
    if not user_state.in_free_search:
        user_state.in_free_search = True
        await update.message.reply_text("🔍 Free search mode activated! Searching for student records...")

    # Send status message
    status_msg = await update.message.reply_text(f"⏳ Searching for: <b>{text}</b>...", parse_mode="HTML")
    
    await update.message.reply_chat_action("typing")
    results = free_search(text)
    user_state.last_search_query = text # Store for potential future use or context
    user_state.free_search_results = results # Store all results for pagination
    user_state.free_search_page = 1 # Reset to first page

    if not results:
        await status_msg.edit_text(f"❌ No records found for: <b>{text}</b>", parse_mode="HTML")
        await update.message.reply_text(
            "😞 No students found matching your search.\n\n"
            "Try searching with:\n"
            "• Different spelling\n"
            "• Roll No instead of name\n"
            "• Mobile number\n"
            "• Aadhaar number",
            parse_mode="HTML"
        )
        return
    
    # Update status with results count
    total_results = len(results)
    page_size = 10
    total_pages = (total_results + page_size - 1) // page_size
    await status_msg.edit_text(f"✅ Found {total_results} student(s)! Loading page 1/{total_pages}...", parse_mode="HTML")
    
    # Display first page of results
    start_idx = 0
    end_idx = min(page_size, total_results)
    
    for res in results[start_idx:end_idx]:
        # Extract year from table_name safely
        year_match = re.search(r'\d+', res.table_name) if res.table_name else None
        year = year_match.group() if year_match else 'N/A'
        
        caption = (
            f"👤 <b>{res.cname}</b> (Year: {year})\n"
            f"📘 Roll: <code>{res.rollno}</code>\n"
            f"📞 Mobile: <code>{res.mobile if res.mobile else 'N/A'}</code>\n"
            f"🆔 Aadhaar: <code>{res.adhaar if res.adhaar else 'N/A'}</code>"
        )
        # Only show Generate Report button, no View Details button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Generate Report", callback_data=f"report_{res.rollno}")]
        ])

        if res.FULL_PHOTO_URL:
            photo_binary = fetch_binary_content(res.FULL_PHOTO_URL)
            if photo_binary:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=InputFile(photo_binary, filename=f"{res.rollno}_photo.jpg"),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=caption + "\n(Photo not available)",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=caption + "\n(Photo not available)",
                parse_mode="HTML",
                reply_markup=keyboard
            )
    
    # Add pagination buttons if there are more results
    if total_pages > 1:
        nav_keyboard = []
        nav_row = []
        if user_state.free_search_page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"free_search_next_{user_state.free_search_page}"))
        nav_row.append(InlineKeyboardButton(f"Page {user_state.free_search_page}/{total_pages}", callback_data="ignore_page"))
        nav_keyboard.append(nav_row)
        
        await update.message.reply_text(
            f"📄 Showing {end_idx} of {total_results} results",
            reply_markup=InlineKeyboardMarkup(nav_keyboard)
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    user_state = get_user_state(user_id)

    try:
        await query.answer()
    except Exception as e:
        print(f"[ERROR] Failed to answer callback query: {e}")
    
    # --- Free Search Flow ---
    if data == "free_search":
        await free_search_handler(update, context)
    
    # --- Guided Search Flow ---
    elif data == "start_guided":
        user_state.reset() # Reset state for new guided search
        user_state.in_free_search = False
        years = get_distinct_years()
        if not years:
            await query.edit_message_text("❌ No academic years found.")
            return
        year_options = [f"{y}-{y+4}" for y in years]
        user_state.years_cache = [y for y in years]
        await query.edit_message_text(
            "📚 <b>Guided Search Started</b>\n\n"
            "📍 Step 1 of 4: Academic Year\n\n"
            "Please select an academic year:",
            parse_mode="HTML",
            reply_markup=build_keyboard(year_options, "year", user_state=user_state)
        )
    elif data.startswith("year_idx_"):
        idx = int(data.split("_")[-1])
        if idx < 0 or idx >= len(user_state.years_cache):
            await query.answer("❌ Invalid selection. Please try again.")
            return
        user_state.year = user_state.years_cache[idx]
        await query.answer(f"✅ Year selected: {user_state.year}-{user_state.year+4}")
        colleges = get_distinct_colleges(user_state.year)
        if not colleges:
            await query.edit_message_text("No colleges found for this year.", reply_markup=build_keyboard([], "start_guided", user_state=user_state))
            return
        user_state.colleges_cache = colleges
        await query.edit_message_text(
            f"✅ Year: {user_state.year}-{user_state.year+4}\n\n"
            f"📍 Step 2 of 4: College\n\n"
            f"Please select a college:",
            parse_mode="HTML",
            reply_markup=build_keyboard(colleges, "college", user_state=user_state)
        )
    elif data.startswith("college_idx_"):
        idx = int(data.split("_")[-1])
        if idx < 0 or idx >= len(user_state.colleges_cache):
            await query.answer("❌ Invalid selection. Please try again.")
            return
        user_state.college = user_state.colleges_cache[idx]
        user_state.course = None
        user_state.subject = None
        user_state.page = 1
        await query.answer(f"✅ College selected: {user_state.college}")

        courses = get_distinct_courses(user_state.year, user_state.college)
        print(f"[DEBUG] Year: {user_state.year}, College: {user_state.college}, Courses found: {courses}")
        
        if not courses:
            # Try fetching without college filter as fallback
            courses = get_distinct_courses(user_state.year)
            print(f"[DEBUG] Fallback - Courses without college filter: {courses}")
            if not courses:
                await query.edit_message_text("❌ No honours/majors found for this college.", reply_markup=build_keyboard([], "start_guided", user_state=user_state))
                return
        
        user_state.courses_cache = courses
        await query.edit_message_text(
            f"✅ Year: {user_state.year}-{user_state.year+4}\n"
            f"✅ College: {user_state.college}\n\n"
            f"📍 Step 3 of 4: Honours\n\n"
            f"Please select a honours/subject:",
            parse_mode="HTML",
            reply_markup=build_keyboard(courses, "course", user_state=user_state)
        )
    elif data.startswith("course_idx_"):
        idx = int(data.split("_")[-1])
        if idx < 0 or idx >= len(user_state.courses_cache):
            await query.answer("❌ Invalid selection. Please try again.")
            return
        user_state.course = user_state.courses_cache[idx]  # This is actually Honours/Major
        user_state.page = 1 # Reset page for students

        print(f"[DEBUG] Fetching students - Year: {user_state.year}, College: {user_state.college}, Honours/Major: {user_state.course}")

        # Fetch students for selected year, college, and honours with pagination (50 per page)
        result = get_students_paginated(
            year=user_state.year, 
            college=user_state.college, 
            subject=user_state.course,  # This filters by allotedhonours
            page=user_state.page,
            page_size=50  # Show 50 students per page
        )
        print(f"[DEBUG] Students found: {result.total_items} total, current page: {result.current_page}/{result.total_pages}")
        
        if result.total_items == 0:
            await query.edit_message_text("❌ No students found for this selection.", reply_markup=build_keyboard([], "start_guided", user_state=user_state))
            return
        
        students = result.items
        keyboard = []
        for idx, student in enumerate(students):
            name = student.get("cname", "Unknown")
            roll = student.get("rollno", "N/A")
            keyboard.append([InlineKeyboardButton(f"{name} ({roll})", callback_data=f"view_student_{idx}")])
        
        # Add pagination buttons if needed
        pagination_btns = []
        if result.current_page > 1:
            pagination_btns.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"student_list_prev_{result.current_page}"))
        if result.current_page < result.total_pages:
            pagination_btns.append(InlineKeyboardButton("Next ➡️", callback_data=f"student_list_next_{result.current_page}"))
        
        if pagination_btns:
            keyboard.append(pagination_btns)
        
        # Store pagination info and students for this page
        user_state.students_list = students
        user_state.current_result = result  # Store full result for pagination
        
        await query.edit_message_text(
            f"✅ Year: {user_state.year}-{user_state.year+4}\n"
            f"✅ College: {user_state.college}\n"
            f"✅ Honours: {user_state.course}\n\n"
            f"📍 Step 4 of 4: Select Student\n\n"
            f"Found <b>{result.total_items}</b> student(s). Page <b>{result.current_page}</b> of <b>{result.total_pages}</b>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # --- Student List Pagination (Next/Prev) in Guided Search ---
    elif data.startswith("student_list_prev_"):
        current_page = int(data.split("_")[3])
        user_state.page = current_page - 1
        
        # Fetch students for previous page
        result = get_students_paginated(
            year=user_state.year,
            college=user_state.college,
            subject=user_state.course,
            page=user_state.page,
            page_size=50
        )
        
        students = result.items
        keyboard = []
        for idx, student in enumerate(students):
            name = student.get("cname", "Unknown")
            roll = student.get("rollno", "N/A")
            keyboard.append([InlineKeyboardButton(f"{name} ({roll})", callback_data=f"view_student_{idx}")])
        
        # Add pagination buttons
        pagination_btns = []
        if result.current_page > 1:
            pagination_btns.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"student_list_prev_{result.current_page}"))
        if result.current_page < result.total_pages:
            pagination_btns.append(InlineKeyboardButton("Next ➡️", callback_data=f"student_list_next_{result.current_page}"))
        
        if pagination_btns:
            keyboard.append(pagination_btns)
        
        user_state.students_list = students
        user_state.current_result = result
        
        await query.edit_message_text(
            f"✅ Year: {user_state.year}-{user_state.year+4}\n"
            f"✅ College: {user_state.college}\n"
            f"✅ Honours: {user_state.course}\n\n"
            f"📍 Page <b>{result.current_page}</b> of <b>{result.total_pages}</b>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data.startswith("student_list_next_"):
        current_page = int(data.split("_")[3])
        user_state.page = current_page + 1
        
        # Fetch students for next page
        result = get_students_paginated(
            year=user_state.year,
            college=user_state.college,
            subject=user_state.course,
            page=user_state.page,
            page_size=50
        )
        
        students = result.items
        keyboard = []
        for idx, student in enumerate(students):
            name = student.get("cname", "Unknown")
            roll = student.get("rollno", "N/A")
            keyboard.append([InlineKeyboardButton(f"{name} ({roll})", callback_data=f"view_student_{idx}")])
        
        # Add pagination buttons
        pagination_btns = []
        if result.current_page > 1:
            pagination_btns.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"student_list_prev_{result.current_page}"))
        if result.current_page < result.total_pages:
            pagination_btns.append(InlineKeyboardButton("Next ➡️", callback_data=f"student_list_next_{result.current_page}"))
        
        if pagination_btns:
            keyboard.append(pagination_btns)
        
        user_state.students_list = students
        user_state.current_result = result
        
        await query.edit_message_text(
            f"✅ Year: {user_state.year}-{user_state.year+4}\n"
            f"✅ College: {user_state.college}\n"
            f"✅ Honours: {user_state.course}\n\n"
            f"📍 Page <b>{result.current_page}</b> of <b>{result.total_pages}</b>:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    # --- Guided Search: View Student from List ---
    elif data.startswith("view_student_"):
        idx = int(data.split("_")[-1])
        if hasattr(user_state, 'students_list') and idx < len(user_state.students_list):
            student = user_state.students_list[idx]
            rollno = student.get("rollno", "N/A")
            
            # Fetch full student data
            student_data = get_student_details_by_rollno(rollno)
            if student_data:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📄 Generate Report", callback_data=f"report_{rollno}")],
                    [InlineKeyboardButton("🔙 Back to List", callback_data="back_to_students")],
                ])
                
                await query.edit_message_text(
                    f"<b>Student: {student.get('cname', 'N/A')}</b>\n"
                    f"Roll No: {rollno}\n\n"
                    f"<i>Generating report will create a PDF with all details...</i>",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await query.answer("❌ Student data not found", show_alert=True)
        else:
            await query.answer("❌ Invalid student selection", show_alert=True)
    # --- Student Actions (View Details / Generate Report) ---
    elif data.startswith("view_"):
        rollno = data.replace("view_", "")
        await query.answer()
        student_data = get_student_details_by_rollno(rollno)
        if student_data:
            details = "<b>Student Details:</b>\n"
            for field in IMPORTANT_FIELDS:
                if field == "photo" or field == "sign": continue
                value = getattr(student_data, field, "N/A")
                details += f"<b>{field.replace("_", " ").title()}:</b> {value}\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Generate Report", callback_data=f"report_{rollno}")],
                [InlineKeyboardButton("🔙 Back to Students", callback_data="back_to_students")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="start_guided")]
            ])

            # Send new message instead of editing (in case the original was a photo)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=details,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            await query.answer("Student details not found.", show_alert=True)
    
    elif data == "back_to_students":
        # Re-fetch the student list for current filters
        await send_paginated_students(update, context, user_state)

    elif data.startswith("free_search_next_"):
        # Handle Next button for free search pagination
        current_page = int(data.split("_")[-1])
        page_size = 10
        total_results = len(user_state.free_search_results)
        total_pages = (total_results + page_size - 1) // page_size
        next_page = min(current_page + 1, total_pages)
        
        user_state.free_search_page = next_page
        start_idx = (next_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_results)
        
        # Send students for this page
        for res in user_state.free_search_results[start_idx:end_idx]:
            year_match = re.search(r'\d+', res.table_name) if res.table_name else None
            year = year_match.group() if year_match else 'N/A'
            
            caption = (
                f"👤 <b>{res.cname}</b> (Year: {year})\n"
                f"📘 Roll: <code>{res.rollno}</code>\n"
                f"📞 Mobile: <code>{res.mobile if res.mobile else 'N/A'}</code>\n"
                f"🆔 Aadhaar: <code>{res.adhaar if res.adhaar else 'N/A'}</code>"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Generate Report", callback_data=f"report_{res.rollno}")]
            ])

            if res.FULL_PHOTO_URL:
                photo_binary = fetch_binary_content(res.FULL_PHOTO_URL)
                if photo_binary:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=InputFile(photo_binary, filename=f"{res.rollno}_photo.jpg"),
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                else:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=caption + "\n(Photo not available)",
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
            else:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=caption + "\n(Photo not available)",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        
        # Add pagination buttons
        nav_keyboard = []
        nav_row = []
        if next_page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"free_search_prev_{next_page}"))
        nav_row.append(InlineKeyboardButton(f"Page {next_page}/{total_pages}", callback_data="ignore_page"))
        if next_page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"free_search_next_{next_page}"))
        nav_keyboard.append(nav_row)
        
        await query.message.reply_text(
            f"📄 Showing {end_idx - start_idx} results | Page {next_page}/{total_pages}",
            reply_markup=InlineKeyboardMarkup(nav_keyboard)
        )

    elif data.startswith("free_search_prev_"):
        # Handle Previous button for free search pagination
        current_page = int(data.split("_")[-1])
        page_size = 10
        total_results = len(user_state.free_search_results)
        total_pages = (total_results + page_size - 1) // page_size
        prev_page = max(1, current_page - 1)
        
        user_state.free_search_page = prev_page
        start_idx = (prev_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_results)
        
        # Send students for this page
        for res in user_state.free_search_results[start_idx:end_idx]:
            year_match = re.search(r'\d+', res.table_name) if res.table_name else None
            year = year_match.group() if year_match else 'N/A'
            
            caption = (
                f"👤 <b>{res.cname}</b> (Year: {year})\n"
                f"📘 Roll: <code>{res.rollno}</code>\n"
                f"📞 Mobile: <code>{res.mobile if res.mobile else 'N/A'}</code>\n"
                f"🆔 Aadhaar: <code>{res.adhaar if res.adhaar else 'N/A'}</code>"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Generate Report", callback_data=f"report_{res.rollno}")]
            ])

            if res.FULL_PHOTO_URL:
                photo_binary = fetch_binary_content(res.FULL_PHOTO_URL)
                if photo_binary:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=InputFile(photo_binary, filename=f"{res.rollno}_photo.jpg"),
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                else:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=caption + "\n(Photo not available)",
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
            else:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=caption + "\n(Photo not available)",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        
        # Add pagination buttons
        nav_keyboard = []
        nav_row = []
        if prev_page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"free_search_prev_{prev_page}"))
        nav_row.append(InlineKeyboardButton(f"Page {prev_page}/{total_pages}", callback_data="ignore_page"))
        if prev_page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"free_search_next_{prev_page}"))
        nav_keyboard.append(nav_row)
        
        await query.message.reply_text(
            f"📄 Showing {end_idx - start_idx} results | Page {prev_page}/{total_pages}",
            reply_markup=InlineKeyboardMarkup(nav_keyboard)
        )

    elif data.startswith("report_"):
        rollno = data.replace("report_", "")
        await query.answer()
        # Animated loader: send a message, then edit later
        loader_msg = await context.bot.send_message(chat_id=query.message.chat_id, text="⏳ <b>Report generating...</b>\nPlease wait while we prepare your report.", parse_mode="HTML")
        try:
            student_data = get_student_details_by_rollno(rollno)
            if not student_data:
                await context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=loader_msg.message_id, text="❌ Student data not found for report generation.")
                return
            output_filename = f"{rollno}_report.jpg"
            report_path = generate_report(student_data.dict(), output_filename)
            if report_path and report_path.exists():
                with open(report_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=InputFile(f, filename=output_filename),
                        caption="📄 Here is your student report."
                    )
                await context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=loader_msg.message_id, text="✅ Report generated successfully!")
            else:
                await context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=loader_msg.message_id, text="❌ Report generation failed. Please try again later.")
        except Exception as e:
            await context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=loader_msg.message_id, text=f"❌ Error: {str(e)}\nPlease try again or contact support.")

async def safe_reply_text(message, text, retries=3):
    for attempt in range(retries):
        try:
            await message.reply_text(text)
            return
        except error.TimedOut:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                print("[BOT] Failed to send message after retries.")
                return

def run_telegram_bot():
    """Starts the Telegram bot in polling mode."""
    print("[BOT] Initializing Telegram Bot...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))

    print("[BOT] Bot Running (Polling Mode)... Press Ctrl+C to stop.")
    application.run_polling()
