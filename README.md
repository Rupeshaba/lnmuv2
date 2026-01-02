# LNMU Search and Telegram Bot

This project has been upgraded and refactored into a full API-based and Telegram-bot-integrated system, while preserving core functionalities like dynamic SQLite database download and report generation.

## Architecture Overview

The project is structured into the following layers:

-   **`config/`**: Contains `config.py` for all global configurations (DB paths, URLs, bot token, etc.).
-   **`database/`**: Contains `database.py` for all SQLite database interactions, including dynamic DB download and index creation.
-   **`schemas/`**: Contains `schemas.py` for Pydantic models, defining data structures for API requests and responses.
-   **`logic/`**: Contains `logic.py` with the core business logic, including data normalization, free search, and guided search functionalities.
-   **`report_templates/`**: Stores JSON/YAML templates for flexible report generation.
-   **`report_generator.py`**: Handles loading report templates and generating image-based reports (without QR codes).
-   **`api/`**: Contains `api.py` which implements the FastAPI application with all required endpoints.
-   **`telegram_bot/`**: Contains `telegram_bot.py` which implements the Telegram bot logic, interacting with the `logic` and `report_generator` modules.
-   **`main.py`**: The main entry point of the application, responsible for initializing the database, starting the FastAPI server, and launching the Telegram bot.
-   **`requirements.txt`**: Lists all Python dependencies.

## Features

-   **Dynamic Database Download**: Automatically downloads `LNMU.db` from a configured URL on startup if not present.
-   **FastAPI Backend**: Exposes a RESTful API for searching student data, fetching details, and generating reports.
-   **Telegram Bot Integration**: A fully functional Telegram bot that allows users to search for students using both free-text queries and guided search options.
-   **Template-Based Report Generation**: Generates clean, government-style student reports based on configurable JSON/YAML templates.
-   **Data Normalization**: Cleans and formats raw database data before display or use (e.g., Title Case for names, date formatting, handling "NULL" strings).
-   **Multi-Table Search**: Searches across `lnmu_ugentrance23`, `lnmu_ugentrance24`, and `lnmu_ugentrance25` tables.
-   **Automatic Indexing**: Creates necessary database indexes on first run for improved search performance.
-   **Pagination**: Supports pagination for guided search results (e.g., student lists).
-   **No Security Restrictions**: As per requirements, there are no security restrictions, masking, or verification steps.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd lnmusearch-main
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure your Telegram Bot Token:**
    Edit `config/config.py` and replace `
