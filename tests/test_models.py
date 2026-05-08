import pytest

from thesegrid import ConnectionRequest, EconomicAssumptions


def test_connection_request_rejects_non_positive_requested_mw():
    with pytest.raises(ValueError, match="requested_mw"):
        ConnectionRequest(network_code="toy", bus_id=1, requested_mw=0)


def test_connection_request_defaults_to_bess_and_documented_economics():
    request = ConnectionRequest(network_code="toy", bus_id=1, requested_mw=2.5)

    assert request.asset == "bess"
    assert request.economics == EconomicAssumptions()
    assert request.reinforcement_wait_years == 5.0


def test_connection_request_rejects_non_bess_asset_for_v1():
    with pytest.raises(ValueError, match="BESS"):
        ConnectionRequest(network_code="toy", bus_id=1, requested_mw=1.0, asset="data-center")
