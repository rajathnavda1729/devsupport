import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "devkit" / "tools"


class ToolTestCase(unittest.TestCase):
    """Runs devkit tools as subprocesses inside a temp project dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_tool(self, tool, *args, check=True, stdin_text=None, cwd=None):
        env = {**os.environ, "NO_COLOR": "1"}
        env.pop("DEVKIT_FEATURE", None)
        p = subprocess.run([sys.executable, str(TOOLS / tool), *map(str, args)], cwd=cwd or self.cwd,
                           capture_output=True, text=True, env=env, timeout=60,
                           input=stdin_text if stdin_text is not None else "",)
        if check and p.returncode != 0:
            self.fail(f"{tool} {args} exited {p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}")
        return p
