"""
AutoSRE — Sandboxed Code Executor
Execute Python code in a sandboxed subprocess with timeout enforcement.
"""

import logging
import subprocess
import sys
import tempfile
import os
from typing import Any, Dict

logger = logging.getLogger("autosre.tools.code_executor")


def execute_python(code: str, timeout: int = 30) -> Dict[str, Any]:
    """Execute Python code in a sandboxed subprocess.
    
    Returns stdout, stderr, and exit code.
    """
    logger.info(f"[execute_python] Running code ({len(code)} chars, timeout={timeout}s)")

    # Write code to a temp file
    tmp_dir = os.path.join(tempfile.gettempdir(), "autosre_sandbox")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_file = os.path.join(tmp_dir, "sandbox_script.py")

    try:
        with open(tmp_file, "w") as f:
            f.write(code)

        result = subprocess.run(
            [sys.executable, tmp_file],
            capture_output=True, text=True, timeout=timeout,
            cwd=tmp_dir,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        return {
            "status": "completed",
            "exit_code": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Execution exceeded {timeout}s timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        try:
            os.remove(tmp_file)
        except Exception:
            pass


def read_file(path: str) -> Dict[str, Any]:
    """Read a file's contents (sandboxed to safe paths)."""
    logger.info(f"[read_file] Reading: {path}")
    # Simulated file reads for demo
    simulated_files = {
        "order_validator.py": '''class OrderValidator:
    def validate(self, order):
        # BUG: Missing null check on shipping_address
        address = order.shipping_address  # <-- NPE when shipping_address is None
        if not address.street:
            raise ValueError("Street required")
        return True
''',
        "checkout_handler.py": '''from order_validator import OrderValidator

class CheckoutHandler:
    def process(self, order):
        validator = OrderValidator()
        validator.validate(order)  # Line 89 — calls into NPE
        return self.charge_payment(order)
''',
    }

    basename = os.path.basename(path)
    if basename in simulated_files:
        return {"path": path, "content": simulated_files[basename], "status": "success"}
    return {"path": path, "content": "", "status": "not_found"}


def write_file(path: str, content: str) -> Dict[str, Any]:
    """Write content to a file (sandboxed)."""
    logger.info(f"[write_file] Writing to: {path} ({len(content)} chars)")
    return {"path": path, "bytes_written": len(content), "status": "simulated"}
