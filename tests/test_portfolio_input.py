from __future__ import annotations

import io

import pytest

from thesegrid.portfolio_input import PortfolioInputError, load_portfolio_sites


def test_load_portfolio_sites_parses_required_and_optional_fields():
    source = io.StringIO(
        "client_site_id,latitude,longitude,requested_mw,storage_duration_hours,"
        "land_control_status,target_connection_date,max_connection_distance_km,"
        "preferred_voltage_kv,project_notes\n"
        "SITE-01,48.8566,2.3522,100,2,option,2028-09-30,35,225,Near industrial zone\n"
    )

    sites = load_portfolio_sites(source)

    assert len(sites) == 1
    site = sites[0]
    assert site.client_site_id == "SITE-01"
    assert site.latitude == pytest.approx(48.8566)
    assert site.longitude == pytest.approx(2.3522)
    assert site.requested_mw == pytest.approx(100.0)
    assert site.storage_duration_hours == pytest.approx(2.0)
    assert site.land_control_status == "option"
    assert site.target_connection_date == "2028-09-30"
    assert site.max_connection_distance_km == pytest.approx(35.0)
    assert site.preferred_voltage_kv == pytest.approx(225.0)
    assert site.project_notes == "Near industrial zone"


def test_load_portfolio_sites_accepts_only_required_columns():
    source = io.StringIO(
        "client_site_id,latitude,longitude,requested_mw,storage_duration_hours\n"
        "SITE-01,43.7,-0.26,50,4\n"
    )

    (site,) = load_portfolio_sites(source)

    assert site.land_control_status is None
    assert site.max_connection_distance_km is None
    assert site.preferred_voltage_kv is None


def test_load_portfolio_sites_reports_all_row_errors_without_silent_correction():
    source = io.StringIO(
        "client_site_id,latitude,longitude,requested_mw,storage_duration_hours,"
        "max_connection_distance_km\n"
        "SITE-01,95,2,0,4,-1\n"
        "SITE-01,48,190,50,-2,20\n"
        ",47,3,20,2,10\n"
    )

    with pytest.raises(PortfolioInputError) as exc_info:
        load_portfolio_sites(source)

    message = str(exc_info.value)
    assert "row 2: latitude must be between -90 and 90" in message
    assert "row 2: requested_mw must be greater than 0" in message
    assert "row 2: max_connection_distance_km must be greater than 0" in message
    assert "row 3: duplicate client_site_id 'SITE-01'" in message
    assert "row 3: longitude must be between -180 and 180" in message
    assert "row 3: storage_duration_hours must be greater than 0" in message
    assert "row 4: client_site_id is required" in message


def test_load_portfolio_sites_rejects_missing_required_columns():
    source = io.StringIO(
        "client_site_id,latitude,longitude,requested_mw\n"
        "SITE-01,48,2,50\n"
    )

    with pytest.raises(PortfolioInputError, match="missing required columns: storage_duration_hours"):
        load_portfolio_sites(source)


def test_load_portfolio_sites_rejects_non_numeric_values_and_empty_portfolio():
    invalid = io.StringIO(
        "client_site_id,latitude,longitude,requested_mw,storage_duration_hours\n"
        "SITE-01,north,2,fifty,4h\n"
    )

    with pytest.raises(PortfolioInputError) as exc_info:
        load_portfolio_sites(invalid)

    assert "row 2: latitude must be a number" in str(exc_info.value)
    assert "row 2: requested_mw must be a number" in str(exc_info.value)
    assert "row 2: storage_duration_hours must be a number" in str(exc_info.value)

    empty = io.StringIO(
        "client_site_id,latitude,longitude,requested_mw,storage_duration_hours\n"
    )
    with pytest.raises(PortfolioInputError, match="portfolio contains no sites"):
        load_portfolio_sites(empty)
