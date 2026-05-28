import json

from thesegrid.cli import main
from thesegrid.client_network import validate_client_network, write_client_network_validation


def test_validate_client_network_accepts_minimum_static_package(tmp_path):
    package = _write_valid_client_network(tmp_path)

    result = validate_client_network(package)

    assert result.valid is True
    assert result.errors == ()
    assert result.package_path == package
    assert result.metadata["schema_version"] == "thesegrid-client-network-v1"
    assert result.metadata["data_source_type"] == "client_model"
    assert result.checked_files["buses.csv"] == "present"
    assert result.checked_files["transformers.csv"] == "optional_missing"


def test_validate_client_network_reports_missing_required_columns(tmp_path):
    package = _write_valid_client_network(tmp_path)
    (package / "lines.csv").write_text(
        "line_id,from_bus,to_bus,length_km,in_service\n"
        "0,0,1,1.0,true\n",
        encoding="utf-8",
    )

    result = validate_client_network(package)

    assert result.valid is False
    assert any("lines.csv missing required columns" in error for error in result.errors)
    assert any("r_ohm_per_km" in error for error in result.errors)
    assert any("max_i_ka" in error for error in result.errors)


def test_write_client_network_validation_outputs_json_and_markdown(tmp_path):
    package = _write_valid_client_network(tmp_path)
    output = tmp_path / "validation"
    result = validate_client_network(package)

    paths = write_client_network_validation(result, output)

    assert paths.json_path == output / "client_network_validation.json"
    assert paths.markdown_path == output / "client_network_validation.md"
    payload = json.loads(paths.json_path.read_text(encoding="utf-8"))
    assert payload["valid"] is True
    markdown = paths.markdown_path.read_text(encoding="utf-8")
    assert "# Client Network Validation" in markdown
    assert "status: valid" in markdown
    assert "data_source_type: client_model" in markdown


def test_cli_validate_client_network_writes_outputs(tmp_path):
    package = _write_valid_client_network(tmp_path)
    output = tmp_path / "cli-validation"

    exit_code = main(
        [
            "validate-client-network",
            "--client-network",
            str(package),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert (output / "client_network_validation.json").exists()
    assert (output / "client_network_validation.md").exists()


def _write_valid_client_network(tmp_path):
    package = tmp_path / "client_network"
    package.mkdir()
    (package / "metadata.yaml").write_text(
        "\n".join(
            [
                "schema_version: thesegrid-client-network-v1",
                "data_source_type: client_model",
                "network_name: pilot_network",
                "country: FR",
                "voltage_level: MV",
                "created_by: client",
                "created_at: 2026-05-28",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package / "constraints.yaml").write_text(
        "\n".join(
            [
                "voltage_min_pu: 0.95",
                "voltage_max_pu: 1.05",
                "max_loading_percent: 100.0",
                "candidate_asset: bess",
                "candidate_power_factor: 1.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package / "buses.csv").write_text(
        "bus_id,name,vn_kv,in_service\n"
        "0,source,20,true\n"
        "1,candidate,20,true\n",
        encoding="utf-8",
    )
    (package / "lines.csv").write_text(
        "line_id,from_bus,to_bus,length_km,r_ohm_per_km,x_ohm_per_km,c_nf_per_km,max_i_ka,in_service\n"
        "0,0,1,1.0,0.1,0.1,0.0,0.35,true\n",
        encoding="utf-8",
    )
    (package / "loads.csv").write_text(
        "load_id,bus_id,p_mw,q_mvar,in_service\n"
        "0,1,0.2,0.02,true\n",
        encoding="utf-8",
    )
    return package
