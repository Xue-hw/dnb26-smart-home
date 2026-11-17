"""Execute the actual shared firmware headers against host serial/EEPROM fakes."""
from pathlib import Path
import os
import re
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("name", ["pin_store_test", "link_test", "uno1_test", "uno2_test"])
def test_firmware_headers(name, tmp_path):
    compiler = os.environ.get("CXX") or shutil.which("c++") or shutil.which("g++")
    if not compiler:
        pytest.skip("Host C++ compiler unavailable; Arduino target compilation is separate")
    directory = Path(__file__).parent
    if name in ("uno1_test", "uno2_test"):
        # Reproduce Arduino's function declaration step for the actual sketch.
        board = "Uno1_Environment_Garage" if name == "uno1_test" else "Uno2_RFID_Door"
        sketch = (directory.parent / board / (board + ".ino")).read_text(encoding="utf-8")
        prototypes = re.findall(r"^((?:void|bool|char|int|byte|const char)\s*\*?\w+\([^\n]*\))\s*\{", sketch, re.M)
        (tmp_path / "firmware_prototypes.h").write_text(
            "\n".join(prototype + ";" for prototype in prototypes), encoding="utf-8")
    executable = tmp_path / (name + (".exe" if os.name == "nt" else ""))
    command = [compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror",
               "-I", str(directory / "stubs"),
               "-I", str(tmp_path),
               "-I", str(directory.parent / "libraries" / "DnbLink" / "src"),
               str(directory / (name + ".cpp")), "-o", str(executable)]
    if os.name == "nt":
        command.extend(["-static-libstdc++", "-static-libgcc"])
    built = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert built.returncode == 0, built.stdout + built.stderr
    checked = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
    assert checked.returncode == 0, checked.stdout + checked.stderr
