import json
import yaml
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import textwrap
import qrcode

from config.config import LOGO_PATH, MAX_REPORT_WIDTH, TEMP_REPORTS_DIR
from logic.logic import fetch_binary_content, safe_open_image, clean_value

# Ensure temp directory exists
Path(TEMP_REPORTS_DIR).mkdir(exist_ok=True)

def load_font(font_name, size):
    try: return ImageFont.truetype(font_name, size)
    except:
        try: return ImageFont.truetype("arial.ttf", size)
        except: return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    if not text: return [""]
    words = text.split()
    line = words[0]
    out=[]
    for w in words[1:]: # Fix for Python 3.10+ incompatible textwrap
        if draw.textlength(line+" "+w, font=font)<=max_width:
            line+=" "+w
        else:
            out.append(line)
            line=w
    out.append(line)
    return out

def ensure_canvas_height(img, draw, required_h, bg="white", buffer=100):
    W, H = img.size
    if required_h + buffer <= H:
        return img, draw
    new_h = max(required_h + buffer, H * 2) # Ensure significant increase if needed
    new_img = Image.new("RGB", (W, int(new_h)), bg)
    new_img.paste(img, (0, 0))
    new_draw = ImageDraw.Draw(new_img)
    return new_img, new_draw

def load_report_template(template_name: str):
    template_path_json = Path(f"report_templates/{template_name}.json")
    template_path_yaml = Path(f"report_templates/{template_name}.yaml")

    if template_path_json.exists():
        with open(template_path_json, "r", encoding="utf-8") as f:
            return json.load(f)
    elif template_path_yaml.exists():
        with open(template_path_yaml, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    else:
        raise FileNotFoundError(f"Report template {template_name} not found in report_templates/")

def generate_qr_code(student_data: dict, size: int = 250) -> Image.Image:
    """Generate QR code containing comprehensive student information with high quality."""
    try:
        # Create QR data with all available student information
        qr_data_parts = [
            f"Roll: {student_data.get('rollno', '')}",
            f"Name: {student_data.get('cname', '')}",
            f"DOB: {student_data.get('dob', '')}",
            f"Email: {student_data.get('email', '')}",
            f"Phone: {student_data.get('mobile', '')}",
            f"Category: {student_data.get('category', '')}",
            f"Gender: {student_data.get('gender', '')}",
            f"College: {student_data.get('allotedcollege', '')}",
            f"Course: {student_data.get('allotedcourse', '')}",
            f"Honours: {student_data.get('allotedhonours', '')}",
            f"Board: {student_data.get('hboard', '')}",
            f"Reg No: {student_data.get('regno', '')}",
            f"Address: {student_data.get('cadd', '')}",
            f"City: {student_data.get('c_city', '')}",
            f"State: {student_data.get('c_state', '')}",
        ]
        qr_data = "\n".join([part for part in qr_data_parts if part.split(": ")[1]])
        
        # Generate QR code with high error correction for better scannability
        qr = qrcode.QRCode(
            version=None,  # Auto-detect version based on data size
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Highest error correction
            box_size=15,  # Larger box size for better clarity
            border=3,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image without resizing to maintain quality
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        # Resize to desired size with high-quality filter
        qr_img = qr_img.resize((size, size), Image.Resampling.LANCZOS)
        return qr_img
    except Exception as e:
        print(f"[QR CODE ERROR] {e}")
        return None

def generate_report(
    student: dict,
    output_filename: str,
    template_name: str = "default_report_template"
) -> Path | None:
    """
    Generates a student report as an image based on a template.

    Args:
    - **`student`**: A dictionary containing student details.
    - **`output_filename`**: The desired filename for the output report (e.g., "report.jpg").
    - **`template_name`**: (Optional) The name of the template file (e.g., "default_report_template"). Defaults to "default_report_template".

    Returns:
    - `Path`: The path to the generated report file, or `None` if an error occurred.
    """
    try:
        template = load_report_template(template_name)
        layout = template["layout"]
        colors = template["colors"]
        fonts_config = template["fonts"]
        sections_config = template["sections"]

        # Load fonts
        fonts = {}
        for font_key, font_cfg in fonts_config.items():
            fonts[font_key] = load_font(font_cfg["name"], font_cfg["size"])

        W = layout["page_width"]
        H = layout["page_height"]
        margin = layout["margin"]
        header_h = layout["header_height"]
        photo_size = layout["photo_size"]
        line_gap = layout["line_gap"]
        table_row_height = layout["table_row_height"]

        img = Image.new("RGB", (W, H), colors["background"])
        draw = ImageDraw.Draw(img)
        y = margin

        # Load logo
        logo_img = None
        if Path(LOGO_PATH).exists():
            try:
                logo_img = Image.open(LOGO_PATH).convert("RGBA")
            except Exception as e:
                print(f"[REPORT] Error loading logo: {e}")

        # --- HEADER ---
        header_cfg = sections_config["header"]
        draw.rectangle((0, y, W, y + header_h), fill=colors["header_bg"])
        
        # Add subtle header shadow/border effect
        draw.rectangle((0, y + header_h, W, y + header_h + 2), fill="#0f1f35")
        
        for element in header_cfg:
            if element["type"] == "logo" and logo_img:
                logo_resized = logo_img.resize(tuple(element["size"]))
                img.paste(logo_resized, (eval(str(element["position"][0])), eval(str(element["position"][1]))), logo_resized)
            elif element["type"] == "text":
                content = student.get(element["content"], element["content"]) if element["content"] != "university" else "Lalit Narayan Mithila University"
                draw.text(
                    (eval(str(element["position"][0])), eval(str(element["position"][1]))),
                    content,
                    font=fonts[element["font"]],
                    fill=colors[element["color"]]
                )
        y += header_h + 12

        # Decorative divider line
        draw.line((margin, y, W - margin, y), fill=colors["divider"], width=4)
        y += 16

        # --- PERSONAL INFO & PHOTO ---
        personal_info_cfg = sections_config["personal_info"]
        photo_x = margin
        photo_y = y

        # Photo frame
        student_photo_url = student.get("FULL_PHOTO_URL")
        photo = safe_open_image(fetch_binary_content(student_photo_url))

        if photo:
            p = ImageOps.fit(photo, (photo_size, photo_size))
            mask = Image.new("L", (photo_size, photo_size), 0)
            ImageDraw.Draw(mask).ellipse((0,0,photo_size,photo_size), fill=255)
            img.paste(p, (photo_x, photo_y), mask)
            # Draw border around photo
            draw.ellipse((photo_x - 3, photo_y - 3, photo_x + photo_size + 3, photo_y + photo_size + 3), outline=colors["divider"], width=3)
        else:
            draw.ellipse((photo_x - 3, photo_y - 3, photo_x + photo_size + 3, photo_y + photo_size + 3), outline="#aaa", width=3)
            draw.text((photo_x + 40, photo_y + 80), "No Photo", font=fonts["label"], fill="#ccc")

        info_x = photo_x + photo_size + 40
        info_w = W - info_x - margin
        label_x = info_x
        value_x = info_x + 300 # Fixed offset for value

        # Generate and add QR code in upper right corner of personal info section
        qr_img = generate_qr_code(student, size=250)
        if qr_img:
            qr_x = W - margin - 250 - 20
            qr_y = photo_y
            img.paste(qr_img, (qr_x, qr_y))
            # Draw border around QR code
            draw.rectangle((qr_x - 4, qr_y - 4, qr_x + 254, qr_y + 254), outline="#1a3a5c", width=3)

        cur_y = photo_y
        for item in personal_info_cfg:
            if item["type"] == "info_pair":
                label = item["label"]
                value = clean_value(student.get(item["value_field"], ""))

                draw.text((label_x, cur_y), f"{label}:", font=fonts["label"], fill=colors["label_text"])
                
                available_width = info_w - (value_x - info_x)
                vlines = wrap_text(draw, value, fonts["value"], available_width)
                ly = cur_y
                for ln in vlines:
                    draw.text((value_x, ly), ln, font=fonts["value"], fill=colors["value_text"])
                    ly += line_gap
                cur_y = ly + 10
        
        y = max(photo_y + photo_size, cur_y) + 26

        # --- ADMISSION DETAILS ---
        admission_cfg = sections_config["admission_details"]
        ad_padding_top = 80
        ad_padding_bottom = 50
        ad_title_h = 50

        # Calculate dynamic height for admission box
        left_col_lines = []
        right_col_lines = []

        left_label_w = 240 # Fixed width for label
        left_value_w = (W//2) - left_label_w - 100
        right_label_w = 180 # Fixed width for label
        right_value_w = (W//2) - right_label_w - 100

        for item in admission_cfg["left_column"]:
            value = clean_value(student.get(item["value_field"], ""))
            left_col_lines.append(wrap_text(draw, value, fonts["value"], left_value_w))
        for item in admission_cfg["right_column"]:
            value = clean_value(student.get(item["value_field"], ""))
            right_col_lines.append(wrap_text(draw, value, fonts["value"], right_value_w))

        row_heights = []
        max_items_in_cols = max(len(admission_cfg["left_column"]), len(admission_cfg["right_column"]))

        for i in range(max_items_in_cols):
            lh = (len(left_col_lines[i]) if i < len(left_col_lines) else 1) * line_gap + 12
            rh = (len(right_col_lines[i]) if i < len(right_col_lines) else 1) * line_gap + 12
            row_heights.append(max(lh, rh))

        total_rows_h = sum(row_heights)
        ad_box_top = y
        ad_box_left = margin
        ad_box_right = W - margin
        ad_box_bottom = ad_box_top + ad_title_h + ad_padding_top + total_rows_h + ad_padding_bottom

        # Draw admission box with rounded corners effect
        # Shadow effect
        draw.rectangle((ad_box_left + 4, ad_box_top + 4, ad_box_right, ad_box_bottom), outline="#e0e0e0", width=2, fill="#f9f9f9")
        draw.rectangle((ad_box_left, ad_box_top, ad_box_right - 4, ad_box_bottom - 4), outline=colors["admission_box_outline"], width=4, fill=colors["admission_box_fill"])
        
        # Section title with background
        draw.rectangle((ad_box_left, ad_box_top, ad_box_right - 4, ad_box_top + ad_title_h), fill=colors["section_title_bg"])
        draw.text((ad_box_left + 28, ad_box_top + 12), admission_cfg["title"], font=fonts["section"], fill=colors["section_title_text"])

        left_start_x = ad_box_left + 40
        val_left_x = left_start_x + left_label_w
        right_start_x = ad_box_left + (W // 2) + 20
        val_right_x = right_start_x + right_label_w

        cur_row_y = ad_box_top + ad_title_h + ad_padding_top
        for i, height_row in enumerate(row_heights):
            # Left column
            if i < len(admission_cfg["left_column"]):
                item = admission_cfg["left_column"][i]
                label = item["label"]
                draw.text((left_start_x, cur_row_y), f"{label}:", font=fonts["label"], fill=colors["label_text"])
                llines = left_col_lines[i]
                ly = cur_row_y
                for ln in llines:
                    draw.text((val_left_x, ly), ln, font=fonts["value"], fill=colors["value_text"])
                    ly += line_gap

            # Right column
            if i < len(admission_cfg["right_column"]):
                item = admission_cfg["right_column"][i]
                label = item["label"]
                draw.text((right_start_x, cur_row_y), f"{label}:", font=fonts["label"], fill=colors["label_text"])
                rlines = right_col_lines[i]
                ry = cur_row_y
                for rl in rlines:
                    draw.text((val_right_x, ry), rl, font=fonts["value"], fill=colors["value_text"])
                    ry += line_gap
            
            cur_row_y += height_row

        y = ad_box_bottom + 28

        # --- EDUCATIONAL QUALIFICATION TABLE ---
        edu_cfg = sections_config["educational_qualification"]
        table_left = margin
        table_right = W - margin
        table_top = y

        header_h = 60
        num_data_rows = len(edu_cfg["rows"])
        table_height = 50 + header_h + (num_data_rows * table_row_height) + 40
        table_bottom = table_top + table_height

        # Shadow effect
        draw.rectangle((table_left + 4, table_top + 4, table_right, table_bottom), outline="#e0e0e0", width=2, fill="#f9f9f9")
        draw.rectangle((table_left, table_top, table_right - 4, table_bottom - 4), outline=colors["admission_box_outline"], width=4, fill=colors["background"])
        
        # Section title with background
        draw.rectangle((table_left, table_top, table_right - 4, table_top + 50), fill=colors["section_title_bg"])
        draw.text((table_left + 28, table_top + 12), edu_cfg["title"], font=fonts["section"], fill=colors["section_title_text"])

        # Column headers with background
        header_y = table_top + 50
        draw.rectangle((table_left, header_y, table_right - 4, header_y + header_h), fill=colors["table_header_bg"])
        draw.line((table_left, header_y, table_right, header_y), fill=colors["divider"], width=2)
        draw.line((table_left, header_y + header_h, table_right, header_y + header_h), fill=colors["divider"], width=2)
        draw.line((table_left, header_y + header_h, table_right, header_y + header_h), fill=colors["divider"], width=2)
        
        col_x_positions = [table_left + 30]
        current_x = table_left + 30
        for col in edu_cfg["columns"]:
            col_width = (W - 2 * margin - 60) * col["width_ratio"]
            current_x += col_width
            col_x_positions.append(current_x)
        
        # Draw column headers
        for i, col_def in enumerate(edu_cfg["columns"]):
            draw.text((col_x_positions[i], header_y + 16), col_def["label"], font=fonts["table_header"], fill=colors["table_header_text"])
        
        # Draw vertical dividers for columns
        for i in range(1, len(col_x_positions) - 1):
            draw.line((col_x_positions[i], header_y, col_x_positions[i], table_bottom), fill="#ddd", width=1)
        
        # Table rows content with alternating colors
        current_row_y = header_y + header_h
        for row_idx, row_cfg in enumerate(edu_cfg["rows"]):
            # Alternate row colors
            if row_idx % 2 == 1:
                draw.rectangle((table_left, current_row_y, table_right, current_row_y + table_row_height), fill=colors["table_alternate_bg"])
            
            draw.text((col_x_positions[0] + 10, current_row_y + 24), row_cfg["class"], font=fonts["table_value"], fill=colors["value_text"])

            board_value = clean_value(student.get(row_cfg["board_field"], ""))
            board_lines = wrap_text(draw, board_value, fonts["table_value"], col_x_positions[2] - col_x_positions[1] - 20)
            by = current_row_y + 24
            for bl in board_lines:
                draw.text((col_x_positions[1] + 10, by), bl, font=fonts["table_value"], fill=colors["value_text"])
                by += 32

            draw.text((col_x_positions[2] + 10, current_row_y + 24), clean_value(student.get(row_cfg["year_field"], "")), font=fonts["table_value"], fill=colors["value_text"])
            draw.text((col_x_positions[3] + 10, current_row_y + 24), clean_value(student.get(row_cfg["marks_field"], "")), font=fonts["table_value"], fill=colors["value_text"])
            
            # Add % sign to percentage
            percent_val = clean_value(student.get(row_cfg["percent_field"], ""))
            percent_display = f"{percent_val}%" if percent_val else ""
            draw.text((col_x_positions[4] + 10, current_row_y + 24), percent_display, font=fonts["table_value"], fill=colors["value_text"])
            
            # Row bottom border
            draw.line((table_left, current_row_y + table_row_height, table_right, current_row_y + table_row_height), fill="#ddd", width=1)
            current_row_y += table_row_height

        y = table_bottom + 40

        # --- SIGNATURE ---
        signature_cfg = sections_config["signature"]
        sig_w, sig_h = signature_cfg["size"]
        
        # Center signature box horizontally on the page
        sig_x = (W - sig_w) // 2
        sig_y = y + 20

        # Draw main signature box
        draw.rectangle((sig_x, sig_y, sig_x + sig_w, sig_y + sig_h), 
                       outline=colors["divider"], width=2, fill="white")

        student_sign_url = student.get("FULL_SIGN_URL")
        signature_img = safe_open_image(fetch_binary_content(student_sign_url))

        if signature_img:
            # Resize signature to fit within the box with proper aspect ratio
            s = ImageOps.fit(signature_img, (sig_w - 50, sig_h - 50), Image.LANCZOS)
            # Center the signature image within the box
            sig_img_x = sig_x + (sig_w - s.width) // 2
            sig_img_y = sig_y + 10
            img.paste(s, (sig_img_x, sig_img_y), s)
        
        # Signature line - positioned under the box
        line_y = sig_y + sig_h + 15
        line_margin = 80
        draw.line((sig_x + line_margin, line_y, sig_x + sig_w - line_margin, line_y), fill=colors["divider"], width=3)
        
        # Label text - centered below the line
        label_text = signature_cfg["label"]
        # Calculate proper centered positioning using text width
        label_bbox = draw.textbbox((0, 0), label_text, font=fonts["label"])
        label_width = label_bbox[2] - label_bbox[0]
        label_x = sig_x + (sig_w - label_width) // 2
        draw.text((label_x, line_y + 8), label_text, font=fonts["label"], fill=colors["label_text"])
        
        y = line_y + 50

        # Ensure canvas height and crop
        img, draw = ensure_canvas_height(img, draw, y, bg=colors["background"], buffer=40) # Smaller buffer for final crop
        img = img.crop((0,0,W,y+20)) # Final crop

        # Resize if too wide
        if img.width > MAX_REPORT_WIDTH:
            new_h = int(img.height * (MAX_REPORT_WIDTH / img.width))
            img = img.resize((MAX_REPORT_WIDTH, new_h), Image.LANCZOS)

        final_report_path = Path(TEMP_REPORTS_DIR) / output_filename
        img.convert("RGB").save(final_report_path, format="JPEG", quality=85, optimize=True)
        print(f"✔ Report generated: {final_report_path}")
        return final_report_path

    except Exception as e:
        print(f"[REPORT GENERATION ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None
