import io
import json
import time
from pathlib import Path

import anthropic

import config
from modules import db, ocr

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def get_supported_files(folder):
    return [p for p in Path(folder).iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS]


def _collect_error_detail(file_path):
    row = db.get_receipt_by_filename(file_path.name)
    if row and row["scan_error"]:
        return {"file": file_path.name, "error": row["scan_error"]}
    return None


def scan_folder():
    files = get_supported_files(config.RECEIPTS_FOLDER)
    files_found = len(files)
    files_new = 0
    files_processed = 0
    files_errored = 0
    error_details = []

    for file_path in files:
        existing = db.get_receipt_by_filename(file_path.name)

        if existing is None:
            receipt_id = db.insert_receipt(file_path.name, file_path)
            files_new += 1
        elif existing["scan_status"] == "done":
            continue
        else:
            receipt_id = existing["id"]
            if existing["scan_status"] == "error":
                db.reset_receipt_to_pending(receipt_id)

        success = _process_receipt(file_path, receipt_id)
        if success:
            files_processed += 1
        else:
            files_errored += 1
            detail = _collect_error_detail(file_path)
            if detail:
                error_details.append(detail)

        time.sleep(0.3)

    db.log_scan(files_found, files_new, files_processed, files_errored)

    return {
        "found": files_found,
        "new": files_new,
        "processed": files_processed,
        "errors": files_errored,
        "error_details": error_details,
    }


def _process_receipt(file_path, receipt_id):
    try:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            image_bytes = _pdf_to_image_bytes(file_path)
            mime_type = "image/png"
        else:
            image_bytes = file_path.read_bytes()
            mime_type = MIME_TYPES.get(suffix, "image/jpeg")

        data = ocr.extract_receipt_data(image_bytes, mime_type)

        db.delete_line_items(receipt_id)
        db.update_receipt_scan_result(
            receipt_id,
            data.get("date"),
            data.get("company_name"),
            data.get("total_amount"),
            json.dumps(data),
        )
        db.insert_line_items(receipt_id, data.get("line_items", []))
        return True

    except anthropic.RateLimitError:
        db.reset_receipt_to_pending(receipt_id)
        return False
    except Exception as e:
        db.update_receipt_scan_error(receipt_id, str(e)[:500])
        return False


def _pdf_to_image_bytes(pdf_path):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    bitmap = page.render(scale=200 / 72)
    pil_image = bitmap.to_pil()
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return buf.getvalue()
