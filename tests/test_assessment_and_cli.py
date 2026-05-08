from pathlib import Path

from thesegrid import ConnectionRequest, assess_connection
from thesegrid.cli import main
from thesegrid.memo import render_investment_memo
from thesegrid.networks import load_network


def test_assess_connection_produces_investment_memo_for_toy_network():
    request = ConnectionRequest(network_code="toy", bus_id=1, requested_mw=0.5)

    memo = assess_connection(request, net=load_network("toy"))

    assert memo.verdict == "go"
    assert memo.firm_injection_mw >= 0.45
    assert memo.firm_withdrawal_mw >= 0.45
    assert memo.recommended_envelope == "firm-only"


def test_render_investment_memo_includes_decision_assumptions_and_uncertainty():
    request = ConnectionRequest(network_code="toy", bus_id=1, requested_mw=0.5)
    memo = assess_connection(request, net=load_network("toy"))

    rendered = render_investment_memo(memo)

    assert "# Flexible Connection Pre-Feasibility Memo" in rendered
    assert "Verdict" in rendered
    assert "Assumptions" in rendered
    assert "Remaining Scientific Uncertainty" in rendered
    assert "does not replace an official grid-connection study" in rendered


def test_cli_assess_writes_reproducible_memo(tmp_path):
    output = tmp_path / "memo.md"

    exit_code = main(
        [
            "assess",
            "--network",
            "toy",
            "--bus",
            "1",
            "--requested-mw",
            "0.5",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.exists()
    assert "network_code: toy" in Path(output).read_text()
