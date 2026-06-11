import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_loads_small_simbench_network_when_dependency_is_available():
    if importlib.util.find_spec("simbench") is None:
        pytest.skip("simbench is not installed in this environment")

    source_dir = Path(__file__).resolve().parents[1] / "src"
    existing_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath = str(source_dir)
    if existing_pythonpath:
        pythonpath = f"{pythonpath}{os.pathsep}{existing_pythonpath}"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from thesegrid.networks import load_network; "
                "net = load_network('1-MV-rural--0-sw'); "
                "print(len(net.bus), len(net.line), len(net.load))"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": pythonpath},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "97 99 96"
