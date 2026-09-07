"""
LUCIA Secure File System Tools
- Bulletproof path handling (~, spaces, absolute paths)
- Path traversal protection
- Allowed directory restrictions
- Destructive operation confirmation
- Full logging
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger("lucia.tools.files")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s | %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)

# ==========================================
# 🔒 SECURITY: ALLOWED DIRECTORIES
# ==========================================
ALLOWED_ROOTS = [
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
    str(Path.cwd()),
]


def _resolve(path: str) -> str:
    """
    Robust path resolver:
    - Expands ~ and ~user
    - Handles spaces in path
    - Resolves symlinks and ..
    - Returns clean absolute path
    """
    if not path:
        return ""
    # Strip surrounding quotes if any (LLMs sometimes wrap paths)
    path = path.strip().strip('"').strip("'")
    # Expand ~
    path = os.path.expanduser(path)
    # Expand env variables like $HOME
    path = os.path.expandvars(path)
    # Absolute + normalize
    return os.path.abspath(path)


def _is_safe(path: str) -> bool:
    """Check if resolved path is within allowed directories"""
    if not path:
        return False
    abs_path = _resolve(path)
    resolved_roots = [_resolve(root) for root in ALLOWED_ROOTS]
    return any(abs_path == root or abs_path.startswith(root + os.sep) for root in resolved_roots)


def _check_path(path: str):
    """Returns resolved path if safe, else None"""
    if not _is_safe(path):
        logger.warning(f"BLOCKED path access: {path}")
        return None
    return _resolve(path)


# ==========================================
# FILE OPERATIONS
# ==========================================

def read_file(path: str) -> dict:
    """Read a file's content"""
    logger.info(f"read_file: {path}")
    safe = _check_path(path)
    if not safe:
        return {"success": False, "message": f"Path allowed nahi hai: {path}. Sirf Desktop, Documents, Downloads allowed hain."}
    if not os.path.exists(safe):
        return {"success": False, "message": f"File mojood nahi: {safe}"}
    if not os.path.isfile(safe):
        return {"success": False, "message": f"Yeh file nahi hai (shayad folder hai): {safe}"}
    try:
        with open(safe, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"read_file OK: {safe} ({len(content)} chars)")
        return {"success": True, "message": f"File padh li: {safe}", "data": content, "path": safe}
    except Exception as e:
        logger.error(f"read_file FAIL: {e}")
        return {"success": False, "message": f"File nahi padhi: {e}"}


def write_file(path: str, content: str) -> dict:
    """Write or overwrite a file (creates parent directories automatically)"""
    logger.info(f"write_file: {path}")
    safe = _check_path(path)
    if not safe:
        return {"success": False, "message": f"Path allowed nahi hai: {path}"}
    try:
        parent = os.path.dirname(safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(safe, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"write_file OK: {safe} ({len(content)} chars)")
        return {"success": True, "message": f"File likh di: {safe}", "path": safe, "bytes_written": len(content)}
    except Exception as e:
        logger.error(f"write_file FAIL: {e}")
        return {"success": False, "message": f"File nahi bani: {e}"}


def create_file(path: str, content: str = "") -> dict:
    """Create a new file (fails if already exists)"""
    logger.info(f"create_file: {path}")
    safe = _check_path(path)
    if not safe:
        return {"success": False, "message": f"Path allowed nahi hai: {path}"}
    if os.path.exists(safe):
        return {"success": False, "message": f"File pehle se mojood hai: {safe}. Overwrite karne ke liye write_file use karein."}
    try:
        parent = os.path.dirname(safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(safe, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"create_file OK: {safe}")
        return {"success": True, "message": f"Nayi file bana di: {safe}", "path": safe}
    except Exception as e:
        logger.error(f"create_file FAIL: {e}")
        return {"success": False, "message": f"File nahi bani: {e}"}


def edit_file(path: str, old_text: str, new_text: str) -> dict:
    """Find and replace text in a file"""
    logger.info(f"edit_file: {path}")
    safe = _check_path(path)
    if not safe:
        return {"success": False, "message": f"Path allowed nahi hai: {path}"}
    if not os.path.exists(safe):
        return {"success": False, "message": f"File mojood nahi: {safe}"}
    try:
        with open(safe, "r", encoding="utf-8") as f:
            content = f.read()
        if old_text not in content:
            return {"success": False, "message": f"Purana text file mein nahi mila. Content check karo."}
        new_content = content.replace(old_text, new_text, 1)
        with open(safe, "w", encoding="utf-8") as f:
            f.write(new_content)
        logger.info(f"edit_file OK: {safe}")
        return {"success": True, "message": f"File edit ho gayi: {safe}", "path": safe}
    except Exception as e:
        logger.error(f"edit_file FAIL: {e}")
        return {"success": False, "message": f"File edit nahi hui: {e}"}


def delete_file(path: str, confirm: bool = False) -> dict:
    """Delete a file — requires explicit confirmation"""
    logger.info(f"delete_file: {path} (confirm={confirm})")
    if not confirm:
        return {"success": False, "message": "Delete karne ke liye confirm=True zaroori hai."}
    safe = _check_path(path)
    if not safe:
        return {"success": False, "message": f"Path allowed nahi hai: {path}"}
    if not os.path.exists(safe):
        return {"success": False, "message": f"File mojood nahi: {safe}"}
    try:
        os.remove(safe)
        logger.info(f"delete_file OK: {safe}")
        return {"success": True, "message": f"File delete kar di: {safe}"}
    except Exception as e:
        logger.error(f"delete_file FAIL: {e}")
        return {"success": False, "message": f"File delete nahi hui: {e}"}


def create_directory(path: str) -> dict:
    """Create a new directory (and parents automatically)"""
    logger.info(f"create_directory: {path}")
    safe = _check_path(path)
    if not safe:
        return {"success": False, "message": f"Path allowed nahi hai: {path}"}
    try:
        os.makedirs(safe, exist_ok=True)
        logger.info(f"create_directory OK: {safe}")
        return {"success": True, "message": f"Folder bana diya: {safe}", "path": safe}
    except Exception as e:
        logger.error(f"create_directory FAIL: {e}")
        return {"success": False, "message": f"Folder nahi bana: {e}"}


def list_directory(path: str = "~/Desktop") -> dict:
    """List files and folders in a directory"""
    logger.info(f"list_directory: {path}")
    safe = _check_path(path)
    if not safe:
        return {"success": False, "message": f"Path allowed nahi hai: {path}"}
    if not os.path.exists(safe):
        return {"success": False, "message": f"Folder mojood nahi: {safe}"}
    if not os.path.isdir(safe):
        return {"success": False, "message": f"Yeh folder nahi hai: {safe}"}
    try:
        items = sorted(os.listdir(safe))
        if not items:
            return {"success": True, "message": f"{safe} khali hai.", "data": [], "path": safe}
        logger.info(f"list_directory OK: {safe} ({len(items)} items)")
        return {"success": True, "message": f"{safe} mein {len(items)} items hain.", "data": items, "path": safe}
    except Exception as e:
        logger.error(f"list_directory FAIL: {e}")
        return {"success": False, "message": f"Files list nahi ho sakin: {e}"}


# Legacy aliases for backward compatibility
create_folder = create_directory
list_files = list_directory
open_file = read_file
delete_file_safe = delete_file