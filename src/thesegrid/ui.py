from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from thesegrid.ui_data import (
    best_resize_rows,
    load_result_bundle,
    manifest_context,
    numeric_column,
    verdict_counts,
)


DEFAULT_RESULTS_DIR = "results/demo_pipeline_full_year"


def main() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="Thesegrid Evidence Console",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_css(st)

    st.sidebar.title("Thesegrid")
    root_text = st.sidebar.text_input("Results folder", value=DEFAULT_RESULTS_DIR)
    root = Path(root_text).expanduser()
    bundle = load_result_bundle(root)
    context = manifest_context(bundle.json_payloads.get("manifest", {}))

    st.markdown(
        """
        <section class="tg-hero">
          <div>
            <p class="tg-kicker">BESS flexible-connection pre-feasibility</p>
            <h1>Evidence console</h1>
            <p class="tg-lede">Decision-first view of screening, QSTS, resize, and
            contractual-envelope artifacts.</p>
          </div>
          <div class="tg-boundary">
            <strong>Boundary</strong>
            <span>Buyer-side pre-feasibility. Not an official RTE/Enedis study, PTF, or offer.</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if not root.exists():
        st.warning(f"Results folder does not exist: {root}")
        _render_empty_state(st)
        return
    if not bundle.artifacts:
        st.warning(f"No Thesegrid result artifacts found under: {root}")
        _render_empty_state(st)
        return

    _render_top_metrics(st, bundle, context)

    tabs = st.tabs(
        [
            "Overview",
            "Bus Ranking",
            "Validation",
            "QSTS Risk",
            "Resize",
            "Envelope",
            "Artifacts",
        ]
    )
    with tabs[0]:
        _render_overview(st, bundle, context)
    with tabs[1]:
        _render_bus_ranking(st, bundle)
    with tabs[2]:
        _render_validation(st, bundle)
    with tabs[3]:
        _render_qsts_risk(st, bundle)
    with tabs[4]:
        _render_resize(st, bundle)
    with tabs[5]:
        _render_envelope(st, bundle)
    with tabs[6]:
        _render_artifacts(st, bundle)


def _render_empty_state(st: Any) -> None:
    st.markdown(
        """
        Start with a pipeline output directory such as:

        ```text
        results/demo_pipeline_full_year
        ```

        Or run the current smoke command from `docs/demo-pipeline.md`, then refresh this
        page.
        """
    )


def _render_top_metrics(st: Any, bundle: Any, context: dict[str, str]) -> None:
    validation = bundle.tables.get("validation", pd.DataFrame())
    qsts = _preferred_qsts(bundle)
    resize = bundle.tables.get("resize", pd.DataFrame())
    metric_columns = st.columns(5)
    metric_columns[0].metric("Network", context.get("network_code") or "-")
    metric_columns[1].metric("Requested MW", _format_optional(context.get("requested_mw")))
    metric_columns[2].metric("Evidence", context.get("evidence_level") or "-")
    metric_columns[3].metric("Validated buses", _validated_bus_count(validation, qsts))
    metric_columns[4].metric("Resize options", _resize_count(resize))


def _render_overview(st: Any, bundle: Any, context: dict[str, str]) -> None:
    left, right = st.columns([1.1, 0.9])
    with left:
        st.subheader("Decision Context")
        context_frame = pd.DataFrame(
            [{"field": key, "value": value or "-"} for key, value in context.items()]
        )
        st.dataframe(context_frame, hide_index=True, use_container_width=True)
    with right:
        st.subheader("Artifact Coverage")
        coverage = pd.DataFrame(
            [
                {"artifact": name, "path": path.as_posix()}
                for name, path in sorted(bundle.artifacts.items())
            ]
        )
        st.dataframe(coverage, hide_index=True, use_container_width=True)

    validation = bundle.tables.get("validation", pd.DataFrame())
    qsts = _preferred_qsts(bundle)
    if not validation.empty and "final_decision" in validation:
        st.subheader("Final Decision Distribution")
        _bar_chart(st, validation, "final_decision")
    elif not qsts.empty and "qsts_verdict" in qsts:
        st.subheader("QSTS Verdict Distribution")
        _bar_chart(st, qsts, "qsts_verdict")

    performance = bundle.json_payloads.get("performance", {})
    if performance:
        st.subheader("Performance")
        st.json(performance, expanded=False)


def _render_bus_ranking(st: Any, bundle: Any) -> None:
    screening = bundle.tables.get("screening", pd.DataFrame())
    if screening.empty:
        st.info("No screening table found.")
        return
    st.subheader("Screening Ranking")
    columns = [
        column
        for column in (
            "rank",
            "bus_id",
            "bus_name",
            "verdict",
            "firm_capacity_mw",
            "conditional_capacity_mw",
            "expected_curtailment_mwh",
            "p90_curtailment_mw",
            "flexible_value_delta_eur",
            "main_constraint",
        )
        if column in screening
    ]
    st.dataframe(screening[columns], hide_index=True, use_container_width=True)

    chart_columns = [column for column in ("firm_capacity_mw", "conditional_capacity_mw") if column in screening]
    if chart_columns and "bus_id" in screening:
        chart = screening[["bus_id", *chart_columns]].copy()
        for column in chart_columns:
            chart[column] = numeric_column(chart, column)
        st.bar_chart(chart.set_index("bus_id"))


def _render_validation(st: Any, bundle: Any) -> None:
    validation = bundle.tables.get("validation", pd.DataFrame())
    if validation.empty:
        st.info("No validation matrix found.")
        return
    st.subheader("Screening To Full-Year Calibration")
    display_columns = [
        column
        for column in (
            "bus_id",
            "bus_name",
            "screening_verdict",
            "qsts_stratified_verdict",
            "qsts_full_year_verdict",
            "selected_policy",
            "standard_policy_verdict",
            "final_decision",
            "calibration_status",
            "recommended_next_action",
            "main_recurring_constraint",
        )
        if column in validation
    ]
    st.dataframe(validation[display_columns], hide_index=True, use_container_width=True)
    if "calibration_status" in validation:
        _bar_chart(st, validation, "calibration_status")


def _render_qsts_risk(st: Any, bundle: Any) -> None:
    qsts = _preferred_qsts(bundle)
    risk = bundle.tables.get("risk_summary", pd.DataFrame())
    frontier = bundle.tables.get("decision_frontier", pd.DataFrame())
    if qsts.empty and risk.empty and frontier.empty:
        st.info("No QSTS risk tables found.")
        return

    if not qsts.empty:
        st.subheader("QSTS Results")
        columns = [
            column
            for column in (
                "rank",
                "bus_id",
                "bus_name",
                "qsts_verdict",
                "validation_level",
                "decision_confidence",
                "p90_curtailment_mw",
                "expected_curtailment_mwh",
                "weighted_curtailment_mwh",
                "curtailment_energy_ratio",
                "main_recurring_constraint",
            )
            if column in qsts
        ]
        st.dataframe(qsts[columns], hide_index=True, use_container_width=True)
        _risk_scatter(st, qsts)

    if not frontier.empty:
        st.subheader("Decision Frontier")
        st.dataframe(frontier, hide_index=True, use_container_width=True)
    if not risk.empty:
        st.subheader("Tail Risk")
        st.dataframe(risk, hide_index=True, use_container_width=True)


def _render_resize(st: Any, bundle: Any) -> None:
    resize = bundle.tables.get("resize", pd.DataFrame())
    if resize.empty:
        st.info("No resize results found.")
        return
    st.subheader("Resize Recommendations")
    best = best_resize_rows(resize)
    if not best.empty:
        st.markdown("Largest acceptable tested MW per bus.")
        st.dataframe(best, hide_index=True, use_container_width=True)
    st.markdown("All resize scenarios.")
    st.dataframe(resize, hide_index=True, use_container_width=True)


def _render_envelope(st: Any, bundle: Any) -> None:
    envelope = bundle.tables.get("contractual_envelope", pd.DataFrame())
    comparison = bundle.tables.get("static_vs_qsts", pd.DataFrame())
    if envelope.empty and comparison.empty:
        st.info("No contractual-envelope artifacts found.")
        return
    if not comparison.empty:
        st.subheader("Static Versus QSTS")
        st.dataframe(comparison, hide_index=True, use_container_width=True)
    if not envelope.empty:
        st.subheader("Contractual Envelope")
        st.dataframe(envelope, hide_index=True, use_container_width=True)
        if {"season", "time_block", "allowed_mw_p10"}.issubset(envelope.columns):
            pivot = envelope.copy()
            pivot["allowed_mw_p10"] = numeric_column(pivot, "allowed_mw_p10")
            grouped = pivot.groupby(["season", "time_block"], as_index=False)["allowed_mw_p10"].min()
            st.bar_chart(grouped.set_index("time_block")["allowed_mw_p10"])


def _render_artifacts(st: Any, bundle: Any) -> None:
    st.subheader("Files")
    rows = [{"artifact": name, "path": path.as_posix()} for name, path in sorted(bundle.artifacts.items())]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _preferred_qsts(bundle: Any) -> pd.DataFrame:
    full_year = bundle.tables.get("qsts_full_year", pd.DataFrame())
    if not full_year.empty:
        return full_year
    return bundle.tables.get("qsts_stratified", pd.DataFrame())


def _validated_bus_count(validation: pd.DataFrame, qsts: pd.DataFrame) -> str:
    if not validation.empty:
        return str(len(validation))
    if not qsts.empty:
        return str(len(qsts))
    return "0"


def _resize_count(resize: pd.DataFrame) -> str:
    if resize.empty:
        return "0"
    if "acceptable" not in resize:
        return str(len(resize))
    return str(len(best_resize_rows(resize)))


def _bar_chart(st: Any, frame: pd.DataFrame, column: str) -> None:
    counts = verdict_counts(frame, column)
    if not counts:
        return
    chart = pd.DataFrame({"count": counts}).sort_index()
    st.bar_chart(chart)


def _risk_scatter(st: Any, frame: pd.DataFrame) -> None:
    if "bus_id" not in frame:
        return
    y_column = "weighted_curtailment_mwh" if "weighted_curtailment_mwh" in frame else "expected_curtailment_mwh"
    if y_column not in frame:
        return
    chart = frame[["bus_id", y_column]].copy()
    chart[y_column] = numeric_column(chart, y_column)
    st.bar_chart(chart.set_index("bus_id"))


def _format_optional(value: str | None) -> str:
    return value if value not in {None, ""} else "-"


def _inject_css(st: Any) -> None:
    st.markdown(
        """
        <style>
          :root {
            --tg-ink: #17201c;
            --tg-muted: #5d6b63;
            --tg-line: #cbd7ce;
            --tg-paper: #f4f3ed;
            --tg-panel: #ffffff;
            --tg-accent: #176b5b;
            --tg-warning: #a66a00;
          }
          .stApp {
            background: var(--tg-paper);
            color: var(--tg-ink);
          }
          section[data-testid="stSidebar"] {
            background: #e8ece6;
            border-right: 1px solid var(--tg-line);
          }
          .tg-hero {
            border-top: 7px solid var(--tg-ink);
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) minmax(260px, .6fr);
            gap: 24px;
            padding: 24px 0 18px;
            margin-bottom: 12px;
          }
          .tg-kicker {
            color: var(--tg-accent);
            font-size: 13px;
            font-weight: 800;
            letter-spacing: .08em;
            margin: 0 0 8px;
            text-transform: uppercase;
          }
          .tg-hero h1 {
            color: var(--tg-ink);
            font-family: Georgia, "Times New Roman", serif;
            font-size: 50px;
            line-height: 1;
            margin: 0 0 10px;
            letter-spacing: 0;
          }
          .tg-lede {
            color: var(--tg-muted);
            font-size: 18px;
            margin: 0;
            max-width: 760px;
          }
          .tg-boundary {
            background: #fff7dd;
            border-left: 5px solid var(--tg-warning);
            display: flex;
            flex-direction: column;
            gap: 8px;
            justify-content: center;
            padding: 16px 18px;
          }
          div[data-testid="stMetric"] {
            background: var(--tg-panel);
            border: 1px solid var(--tg-line);
            padding: 14px 16px;
          }
          div[data-testid="stMetricLabel"] p {
            color: var(--tg-muted);
            font-weight: 700;
          }
          h2, h3 {
            letter-spacing: 0;
          }
          @media (max-width: 860px) {
            .tg-hero {
              grid-template-columns: 1fr;
            }
            .tg-hero h1 {
              font-size: 38px;
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
