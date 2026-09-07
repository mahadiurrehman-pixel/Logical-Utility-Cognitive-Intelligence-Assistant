"""
LUCIA Secure Terminal Command Executor
- Robust cwd handling (~, spaces, absolute paths)
- Command injection prevention
- Dangerous command blocking
- Timeout protection
- Full stdout/stderr/exit_code capture
"""
import os
import re
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("lucia.tools.terminal")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s | %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)

# ==========================================
# 🔒 SECURITY: ALLOWED WORKING DIRECTORIES
# ==========================================
ALLOWED_CWD = [
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
    str(Path.cwd()),
]

# ==========================================
# 🚫 BLOCKED DANGEROUS PATTERNS
# ==========================================
BLOCKED_PATTERNS = [
    r'\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)*/(\s|$)',  # rm -rf /
    r'\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)*~(\s|$)',  # rm -rf ~
    r'\bmkfs\b',
    r'\bdd\s+if=',
    r'\b(shred|wipefs|fdisk|parted)\b',
    r'\bsudo\b',
    r'\bsu\s',
    r'\bchmod\s+777\s+/',
    r'\bchown\s+root\b',
    r'\b(curl|wget)\s+.*\|\s*(bash|sh|python)',
    r'\bnc\s+-[a-zA-Z]*l',
    r'\b(shutdown|reboot|halt|poweroff|init\s+[06])\b',
    r':\(\)\s*\{',
    r'\bunset\s+PATH\b',
]


def _resolve_path(path: str) -> str:
    """Resolve ~, env vars, spaces safely"""
    if not path:
        return ""
    path = path.strip().strip('"').strip("'")
    path = os.path.expanduser(path)
    path = os.path.expandvars(path)
    return os.path.abspath(path)


def _is_cwd_safe(cwd: str) -> bool:
    """Check if working directory is within allowed paths"""
    abs_cwd = _resolve_path(cwd)
    resolved_roots = [_resolve_path(root) for root in ALLOWED_CWD]
    return any(abs_cwd == root or abs_cwd.startswith(root + os.sep) for root in resolved_roots)


def _is_command_safe(command: str):
    """Returns (is_safe, reason)"""
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Blocked pattern: {pattern}"
    return True, ""


def execute_command(command: str, cwd: str = "~/Desktop", timeout: int = 30) -> dict:
    """
    Execute a terminal command safely.
    
    Args:
        command: Shell command to run
        cwd: Working directory (auto-expanded, must be in ALLOWED_CWD)
        timeout: Max seconds before killing (default 30)
    """
    logger.info(f"execute_command: '{command}' in '{cwd}'")
    
    resolved_cwd = _resolve_path(cwd)
    
    if not _is_cwd_safe(resolved_cwd):
        logger.warning(f"BLOCKED cwd: {resolved_cwd}")
        return {
            "success": False,
            "message": f"Working directory '{resolved_cwd}' allowed nahi hai.",
            "stdout": "", "stderr": "", "exit_code": -1
        }
    
    if not os.path.exists(resolved_cwd):
        return {
            "success": False,
            "message": f"Working directory mojood nahi: {resolved_cwd}",
            "stdout": "", "stderr": "", "exit_code": -1
        }
    
    safe, reason = _is_command_safe(command)
    if not safe:
        logger.warning(f"BLOCKED command: {reason}")
        return {
            "success": False,
            "message": f"Yeh command blocked hai: {reason}",
            "stdout": "", "stderr": "", "exit_code": -1
        }
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=resolved_cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        )
        
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        exit_code = result.returncode
        
        max_output = 3000
        if len(stdout) > max_output:
            stdout = stdout[:max_output] + f"\n... (truncated, {len(result.stdout)} total)"
        if len(stderr) > max_output:
            stderr = stderr[:max_output] + f"\n... (truncated)"
        
        success = exit_code == 0
        logger.info(f"execute_command {'OK' if success else 'FAIL'}: exit={exit_code}")
        
        msg_parts = [f"Command run hua (exit={exit_code})."]
        if stdout:
            msg_parts.append(f"Output:\n{stdout}")
        if stderr:
            msg_parts.append(f"Errors:\n{stderr}")
        
        return {
            "success": success,
            "message": "\n".join(msg_parts),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "cwd": resolved_cwd,
        }
        
    except subprocess.TimeoutExpired:
        logger.warning(f"TIMEOUT after {timeout}s")
        return {
            "success": False,
            "message": f"Command {timeout}s mein timeout ho gaya.",
            "stdout": "", "stderr": "Timeout", "exit_code": -1
        }
    except Exception as e:
        logger.error(f"execute_command ERROR: {e}")
        return {
            "success": False,
            "message": f"Command execute nahi hua: {e}",
            "stdout": "", "stderr": str(e), "exit_code": -1
        }