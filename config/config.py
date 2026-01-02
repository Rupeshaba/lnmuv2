import os

# Database configuration
DB_FILE = "LNMU.db"

# IMPORTANT: The Dropbox URL MUST be a direct download link
# To get a direct download link from Dropbox:
# 1. Right-click on file in Dropbox → Share → Create link
# 2. Replace "?dl=0" with "?dl=1" at the end of the URL
# OR use dl.dropboxusercontent.com domain
DROPBOX_DIRECT_URL = "https://www.dropbox.com/scl/fi/0288oe6wk9p96i4q5dv2d/LNMU.db?rlkey=6xcmq0sxwrxafpchgdm7gh3gd&st=cvy6rtgh&dl=1"
GOOGLE_DRIVE_FILE_ID = "1OSlOI7bOvTKzq2d834TOtzm-tehk7fS9"


DB_PATH = os.path.join(os.getcwd(), DB_FILE)

# Tables to search
TABLES = [
    "lnmu_ugentrance23",
    "lnmu_ugentrance24",
    "lnmu_ugentrance25"
]

# Columns for free search and indexing
SEARCH_COLS = [
    "rollno",
    "cname",
    "cadd",
    "mobile",
    "email",
    "adhaar",
    "c_city",
    "c_pincode"
]

# Telegram Bot Token (replace with your actual token)
BOT_TOKEN = "8406048021:AAHqTzcuWloc01VOiU-cABZNfp2CTAdR6QI"

# Base URLs for photo and signature (based on table/year)
BASE_URLS = {
    "lnmu_ugentrance23": "https://lnmuniversity.com/ugentrance23/",
    "lnmu_ugentrance24": "https://lnmuniversity.com/ugentrance24/",
    "lnmu_ugentrance25": "https://lnmuniversity.com/ugentrance25/",
}

# Important fields for report generation and data normalization
IMPORTANT_FIELDS = [
    "cname","fname","mname","dob","gender","category","mobile","email","adhaar",
    "religion","nationality","marrige",
    "cadd","c_city","c_dist","c_state","c_pincode",
    "padd","p_city","p_state","p_pincode",
    "hboard","hyear","hobt","hmarks","hprcnt","hrollno",
    "iboard","iyear","iobt","imarks","iprcnt","irollno",
    "rollno","regno","admdate",
    "allotedcollege","allotedcourse","allotedhonours",
    "stream","spallotedcategory","spallotedcollege","spallotedcourse","spallotedhonours",
    "passingstream","merit","uniregno",
    "photo","sign","identificationMarks","appdt",
    "courseType","major","councelling"
]

# Report generation configuration
LOGO_PATH = "logo.jpeg"
MAX_REPORT_WIDTH = 1080
TEMP_REPORTS_DIR = "temp_reports"

# Pagination settings
STUDENTS_PER_PAGE = 10

