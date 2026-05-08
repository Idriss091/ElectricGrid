import importlib.util
import subprocess
import sys

import pytest


def test_loads_small_simbench_network_when_dependency_is_available():
    if importlib.util.find_spec("simbench") is None:
        pytest.skip("simbench is not installed in this environment")

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
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "97 99 96"
