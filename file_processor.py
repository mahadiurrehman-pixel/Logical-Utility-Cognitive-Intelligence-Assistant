"""
LUCIA Multimodal File Processor
- Central engine for extracting content from uploaded files
- Supports: PDF, DOCX, TXT, CSV, XLSX, Images, Audio
- Returns normalized Attachment records with extractedText or base64
"""
import os
import io
import uuid
import base64
import json
import logging
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("lucia.files")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s | %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)

# ==========================================
# CONFIGURATION
# ==========================================
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory attachment registry (dev mode; use DB for production persistence)
ATTACHMENT_REGISTRY: dict = {}

# File size limits (bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024        # 10 MB
MAX_AUDIO_SIZE = 25 * 1024 * 1024        # 25 MB
MAX_DOCUMENT_SIZE = 20 * 1024 * 1024     # 20 MB
MAX_SPREADSHEET_SIZE = 15 * 1024 * 1024  # 15 MB
MAX_TEXT_SIZE = 5 * 1024 * 1024          # 5 MB

# Text content limit sent to LLM (to prevent context overflow)
MAX_TEXT_CONTEXT_CHARS = 15000

SUPPORTED_TYPES = {
    "image": {"png", "jpg", "jpeg", "webp"},
    "document": {"pdf", "doc", "docx", "txt"},
    "spreadsheet": {"csv", "xls", "xlsx"},
    "audio": {"mp3", "wav", "m4a", "ogg"},
}


# ==========================================
# UTILITIES
# ==========================================
def _get_file_category(extension: str) -> Optional[str]:
    ext = extension.lower().lstrip(".")
    for category, exts in SUPPORTED_TYPES.items():
        if ext in exts:
            return category
    return None


def _sanitize_filename(name: str) -> str:
    """Prevent path traversal by keeping only base filename"""
    return os.path.basename(name).replace("..", "").replace("/", "_").replace("\\", "_")


def _check_size_limit(size: int, category: str) -> Optional[str]:
    limits = {
        "image": MAX_IMAGE_SIZE,
        "audio": MAX_AUDIO_SIZE,
        "document": MAX_DOCUMENT_SIZE,
        "spreadsheet": MAX_SPREADSHEET_SIZE,
    }
    limit = limits.get(category, MAX_TEXT_SIZE)
    if size > limit:
        limit_mb = limit / (1024 * 1024)
        return f"File is too large. Maximum for {category} is {limit_mb:.0f} MB."
    return None


def _truncate_text(text: str) -> str:
    if len(text) <= MAX_TEXT_CONTEXT_CHARS:
        return text
    return text[:MAX_TEXT_CONTEXT_CHARS] + f"\n\n... [content truncated at {MAX_TEXT_CONTEXT_CHARS} chars]"


# ==========================================
# PROCESSING ADAPTERS
# ==========================================
def _process_pdf(file_path: Path) -> dict:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(file_path))
        pages = len(reader.pages)
        text = ""
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            text += f"\n--- Page {i + 1} ---\n{page_text}"
        return {
            "extractedText": _truncate_text(text.strip()),
            "metadata": {"pages": pages, "chars": len(text)}
        }
    except Exception as e:
        logger.error(f"PDF processing failed: {e}")
        return {"extractedText": "", "metadata": {"error": str(e)}}


def _process_docx(file_path: Path) -> dict:
    try:
        from docx import Document
        doc = Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        
        # Extract tables too
        tables_text = []
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join([cell.text.strip() for cell in row.cells])
                tables_text.append(row_text)
        
        full_text = "\n".join(paragraphs)
        if tables_text:
            full_text += "\n\n--- Tables ---\n" + "\n".join(tables_text)
        
        return {
            "extractedText": _truncate_text(full_text),
            "metadata": {"paragraphs": len(paragraphs), "tables": len(doc.tables)}
        }
    except Exception as e:
        logger.error(f"DOCX processing failed: {e}")
        return {"extractedText": "", "metadata": {"error": str(e)}}


def _process_txt(file_path: Path) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return {
            "extractedText": _truncate_text(text),
            "metadata": {"chars": len(text), "lines": text.count("\n") + 1}
        }
    except Exception as e:
        logger.error(f"TXT processing failed: {e}")
        return {"extractedText": "", "metadata": {"error": str(e)}}


def _process_csv(file_path: Path) -> dict:
    try:
        import pandas as pd
        df = pd.read_csv(file_path, nrows=500)  # Limit to prevent huge context
        
        summary = f"CSV file with {len(df)} rows (first 500 shown) and {len(df.columns)} columns.\n"
        summary += f"Columns: {', '.join(df.columns.astype(str).tolist())}\n\n"
        summary += "First 20 rows:\n" + df.head(20).to_string()
        summary += "\n\nStatistical summary of numeric columns:\n" + df.describe().to_string()
        
        return {
            "extractedText": _truncate_text(summary),
            "metadata": {"rows": len(df), "columns": len(df.columns)}
        }
    except Exception as e:
        logger.error(f"CSV processing failed: {e}")
        return {"extractedText": "", "metadata": {"error": str(e)}}


def _process_xlsx(file_path: Path) -> dict:
    try:
        import pandas as pd
        xl = pd.ExcelFile(file_path)
        summary_parts = [f"Spreadsheet with {len(xl.sheet_names)} sheet(s): {', '.join(xl.sheet_names)}\n"]
        
        for sheet_name in xl.sheet_names[:3]:  # Max 3 sheets
            df = pd.read_excel(xl, sheet_name=sheet_name, nrows=200)
            summary_parts.append(
                f"\n=== Sheet: '{sheet_name}' ===\n"
                f"Rows: {len(df)}, Columns: {len(df.columns)}\n"
                f"Columns: {', '.join(df.columns.astype(str).tolist())}\n"
                f"First 15 rows:\n{df.head(15).to_string()}"
            )
        
        summary = "\n".join(summary_parts)
        return {
            "extractedText": _truncate_text(summary),
            "metadata": {"sheets": xl.sheet_names}
        }
    except Exception as e:
        logger.error(f"XLSX processing failed: {e}")
        return {"extractedText": "", "metadata": {"error": str(e)}}


def _process_image(file_path: Path) -> dict:
    """
    For images: keep base64 for vision-capable models, provide fallback description
    """
    try:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        return {
            "extractedText": "",
            "base64Image": b64,
            "metadata": {"bytes": len(image_bytes)}
        }
    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        return {"extractedText": "", "metadata": {"error": str(e)}}


def _process_audio(file_path: Path) -> dict:
    """Transcribe using existing audio_engine"""
    try:
        from audio_engine import transcribe_audio
        with open(file_path, "rb") as f:
            audio_bytes = f.read()
        transcript = transcribe_audio(audio_bytes)
        return {
            "extractedText": _truncate_text(transcript),
            "metadata": {"chars": len(transcript)}
        }
    except Exception as e:
        logger.error(f"Audio processing failed: {e}")
        return {"extractedText": "", "metadata": {"error": str(e)}}


# ==========================================
# MAIN PROCESSING ORCHESTRATOR
# ==========================================
def process_uploaded_file(file_bytes: bytes, original_filename: str) -> dict:
    """
    Central entry point. Validates, saves, and processes file.
    Returns normalized attachment record or error.
    """
    filename = _sanitize_filename(original_filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    category = _get_file_category(extension)
    
    print("─" * 55)
    print("📎 LUCIA FILE PROCESSING")
    print("─" * 55)
    print(f"File     : {filename}")
    print(f"Type     : {category or 'unknown'}")
    print(f"Size     : {len(file_bytes) / 1024:.1f} KB")
    
    if not category:
        print(f"Status   : ✗ Unsupported file type (.{extension})")
        print("─" * 55)
        return {
            "success": False,
            "message": f"LUCIA doesn't support .{extension} files yet.",
        }
    
    size_error = _check_size_limit(len(file_bytes), category)
    if size_error:
        print(f"Status   : ✗ {size_error}")
        print("─" * 55)
        return {"success": False, "message": size_error}
    
    # Save file
    file_id = str(uuid.uuid4())[:12]
    stored_path = UPLOAD_DIR / f"{file_id}_{filename}"
    try:
        with open(stored_path, "wb") as f:
            f.write(file_bytes)
    except Exception as e:
        print(f"Status   : ✗ Storage failed: {e}")
        print("─" * 55)
        return {"success": False, "message": f"Could not save file: {e}"}
    
    print(f"Status   : Processing...")
    print(f"Operation: {category.upper()} extraction")
    
    # Process by type
    try:
        if extension == "pdf":
            result = _process_pdf(stored_path)
        elif extension in ["doc", "docx"]:
            result = _process_docx(stored_path)
        elif extension == "txt":
            result = _process_txt(stored_path)
        elif extension == "csv":
            result = _process_csv(stored_path)
        elif extension in ["xls", "xlsx"]:
            result = _process_xlsx(stored_path)
        elif extension in ["png", "jpg", "jpeg", "webp"]:
            result = _process_image(stored_path)
        elif extension in ["mp3", "wav", "m4a", "ogg"]:
            result = _process_audio(stored_path)
        else:
            result = {"extractedText": "", "metadata": {}}
    except Exception as e:
        print(f"Status   : ✗ Processing error: {e}")
        print("─" * 55)
        return {"success": False, "message": f"Processing failed: {e}"}
    
    # Build attachment record
    mime_type, _ = mimetypes.guess_type(str(stored_path))
    
    attachment = {
        "id": file_id,
        "filename": filename,
        "mimeType": mime_type or "application/octet-stream",
        "size": len(file_bytes),
        "type": category,
        "status": "ready",
        "extractedText": result.get("extractedText", ""),
        "base64Image": result.get("base64Image"),
        "metadata": result.get("metadata", {}),
        "storageReference": str(stored_path),
        "createdAt": datetime.now().isoformat(),
    }
    
    ATTACHMENT_REGISTRY[file_id] = attachment
    
    print(f"Status   : ✓ Success")
    if result.get("metadata"):
        for k, v in result["metadata"].items():
            print(f"{k.capitalize():9}: {v}")
    print("─" * 55)
    
    # Return without base64 in response (frontend doesn't need it)
    response = {k: v for k, v in attachment.items() if k not in ["base64Image", "storageReference", "extractedText"]}
    response["preview"] = attachment["extractedText"][:200] if attachment["extractedText"] else ""
    
    return {"success": True, "attachment": response}


def get_attachment(attachment_id: str) -> Optional[dict]:
    return ATTACHMENT_REGISTRY.get(attachment_id)


def delete_attachment(attachment_id: str) -> bool:
    att = ATTACHMENT_REGISTRY.pop(attachment_id, None)
    if att:
        try:
            path = Path(att["storageReference"])
            if path.exists():
                path.unlink()
        except Exception as e:
            logger.warning(f"Cleanup warning: {e}")
        return True
    return False


def build_attachment_context(attachment_ids: list) -> str:
    """Build a text summary of attached files for LLM context injection"""
    if not attachment_ids:
        return ""
    
    parts = ["=== ATTACHED FILES ===\n"]
    for att_id in attachment_ids:
        att = get_attachment(att_id)
        if not att:
            continue
        
        parts.append(f"\n📎 **{att['filename']}** ({att['type']}, {att['size'] / 1024:.1f} KB)")
        
        if att['type'] == 'image':
            parts.append("[This is an image. If the LLM supports vision, describe/analyze it as requested.]")
        elif att.get('extractedText'):
            parts.append(f"Content:\n{att['extractedText']}")
        else:
            parts.append("[Content could not be extracted.]")
    
    parts.append("\n=== END OF ATTACHMENTS ===\n")
    return "\n".join(parts)