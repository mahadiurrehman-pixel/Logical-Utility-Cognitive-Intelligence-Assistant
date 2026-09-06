import os
from pathlib import Path
import subprocess
import platform

# 🔒 Security: LUCIA sirf in folders mein kaam karegi
ALLOWED_ROOTS = [
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
    str(Path.cwd()),  # Current project folder
]

def _is_safe_path(path: str) -> bool:
    """Ensure path is within allowed directories"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    return any(abs_path.startswith(os.path.abspath(root)) for root in ALLOWED_ROOTS)


def _resolve_path(path: str) -> str:
    """Resolve ~/Desktop style paths"""
    return os.path.abspath(os.path.expanduser(path))


def list_files(folder: str = "~/Desktop") -> dict:
    """List all files in a folder"""
    try:
        path = _resolve_path(folder)
        if not _is_safe_path(path):
            return {"success": False, "message": "Yeh folder allowed nahi hai."}
        if not os.path.exists(path):
            return {"success": False, "message": f"Folder mojood nahi: {path}"}
        
        items = os.listdir(path)
        if not items:
            return {"success": True, "message": f"{folder} khali hai."}
        
        return {"success": True, "message": f"{folder} mein {len(items)} items hain.", "data": items}
    except Exception as e:
        return {"success": False, "message": f"Files list nahi ho sakin: {e}"}


def read_file(path: str) -> dict:
    """Read a file's content"""
    try:
        full_path = _resolve_path(path)
        if not _is_safe_path(full_path):
            return {"success": False, "message": "Yeh file allowed nahi hai."}
        if not os.path.exists(full_path):
            return {"success": False, "message": "File mojood nahi."}
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"success": True, "message": "File padh li.", "data": content}
    except Exception as e:
        return {"success": False, "message": f"File nahi padhi: {e}"}


def write_file(path: str, content: str) -> dict:
    """Write or overwrite a file"""
    try:
        full_path = _resolve_path(path)
        if not _is_safe_path(full_path):
            return {"success": False, "message": "Yeh path allowed nahi hai."}
        
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "message": f"File likh di: {path}"}
    except Exception as e:
        return {"success": False, "message": f"File nahi bani: {e}"}


def create_folder(path: str) -> dict:
    """Create a new folder"""
    try:
        full_path = _resolve_path(path)
        if not _is_safe_path(full_path):
            return {"success": False, "message": "Yeh folder allowed nahi."}
        os.makedirs(full_path, exist_ok=True)
        return {"success": True, "message": f"Folder bana diya: {path}"}
    except Exception as e:
        return {"success": False, "message": f"Folder nahi bana: {e}"}


def open_file(path: str) -> dict:
    """Open file in default OS application"""
    try:
        full_path = _resolve_path(path)
        if not _is_safe_path(full_path):
            return {"success": False, "message": "Yeh file allowed nahi hai."}
        if not os.path.exists(full_path):
            return {"success": False, "message": "File mojood nahi."}
        
        system = platform.system()
        if system == "Linux":
            subprocess.Popen(["xdg-open", full_path])
        elif system == "Darwin":
            subprocess.Popen(["open", full_path])
        elif system == "Windows":
            os.startfile(full_path)
        
        return {"success": True, "message": f"File khol di: {path}"}
    except Exception as e:
        return {"success": False, "message": f"File nahi khuli: {e}"}


def delete_file_safe(path: str, confirm: bool = False) -> dict:
    """Delete a file — ONLY if user confirms"""
    try:
        if not confirm:
            return {"success": False, "message": "Delete karne se pehle confirmation zaroori hai."}
        full_path = _resolve_path(path)
        if not _is_safe_path(full_path):
            return {"success": False, "message": "Yeh file allowed nahi hai."}
        os.remove(full_path)
        return {"success": True, "message": f"File delete kar di: {path}"}
    except Exception as e:
        return {"success": False, "message": f"File delete nahi hui: {e}"}