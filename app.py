"""Streamlit interface for the validated UniMate optimization engine."""

from __future__ import annotations

import hashlib
import json
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from engine import (
    CompatibilityScorer,
    OptimizationConfig,
    RoomOptimizer,
    ScoringConfig,
    parse_student_survey,
)


DEFAULT_SURVEY = os.path.join(os.getcwd(), "Data", "MOCK_DATA-Women.csv")


def load_dataset() -> tuple[pd.DataFrame, str]:
    st.sidebar.subheader("Student questionnaire")
    uploaded = st.sidebar.file_uploader(
        "Upload original survey data",
        type=["csv", "xlsx"],
        help="Use the raw 11-column questionnaire, not a one-hot encoded file.",
    )
    if uploaded is not None:
        if uploaded.name.lower().endswith(".xlsx"):
            return pd.read_excel(uploaded), uploaded.name
        return pd.read_csv(uploaded), uploaded.name
    if os.path.exists(DEFAULT_SURVEY):
        return pd.read_csv(DEFAULT_SURVEY), os.path.basename(DEFAULT_SURVEY)
    return pd.DataFrame(), ""


def optimization_controls() -> tuple[OptimizationConfig, ScoringConfig]:
    st.sidebar.subheader("Assignment settings")
    capacity = st.sidebar.number_input(
        "Room capacity",
        min_value=2,
        max_value=8,
        value=6,
        step=1,
    )
    time_limit = st.sidebar.number_input(
        "Search time limit (seconds)",
        min_value=5,
        max_value=300,
        value=300,
        step=5,
    )
    seed = st.sidebar.number_input(
        "Random seed",
        min_value=0,
        max_value=1_000_000,
        value=42,
        step=1,
    )

    st.sidebar.subheader("Scoring policy")
    sensitivity = st.sidebar.checkbox(
        "Sensitivity-analysis weights",
        value=False,
        help=(
            "Production defaults are fixed and equally weighted. Enable this only "
            "to study how assumptions affect results."
        ),
    )
    if sensitivity:
        weights = {
            "cleanliness": st.sidebar.slider("Cleanliness", 0, 100, 25),
            "noise": st.sidebar.slider("Noise tolerance", 0, 100, 25),
            "study": st.sidebar.slider("Study environment", 0, 100, 25),
            "schedule": st.sidebar.slider("Sleep and wake schedule", 0, 100, 25),
        }
        scoring = ScoringConfig.from_weights(weights)
    else:
        scoring = ScoringConfig()

    optimization = OptimizationConfig(
        capacity=int(capacity),
        time_limit_seconds=float(time_limit),
        seed=int(seed),
    )
    return optimization, scoring


def render_validation(parsed) -> None:
    left, middle, right = st.columns(3)
    left.metric("Students", f"{len(parsed.data):,}")
    middle.metric("Validation errors", parsed.error_count)
    right.metric("Validation warnings", parsed.warning_count)
    if parsed.issues:
        with st.expander("Validation report", expanded=not parsed.is_valid):
            st.dataframe(parsed.validation_report(), width="stretch")


def render_results(result, students: pd.DataFrame) -> None:
    st.success(
        "Assignment completed. Status: best solution found within the configured "
        "search budget; global optimality is not claimed."
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Worst student utility", f"{result.metrics.min_student_utility:.1f}")
    col2.metric("10th percentile room", f"{result.metrics.p10_room_quality:.1f}")
    col3.metric("Mean student utility", f"{result.metrics.mean_student_utility:.1f}")
    col4.metric("Runtime", f"{result.runtime_seconds:.1f}s")

    st.subheader("Room quality")
    figure = px.histogram(
        result.room_metrics,
        x="room_quality",
        nbins=20,
        title="Distribution of weakest-student utility by room",
    )
    st.plotly_chart(figure, width="stretch")

    profile_fields = [
        field
        for field in (
            "student_idx",
            "faculty",
            "major",
            "age",
            "sleep_window",
            "wake_window",
            "noise_tolerance",
            "study_habit",
            "cleanliness",
        )
        if field in students.columns
    ]
    ledger = result.assignments.merge(
        students[profile_fields],
        on="student_idx",
        how="left",
    )
    st.subheader("Assignments")
    st.dataframe(ledger, width="stretch", hide_index=True)

    st.subheader("Explainability by room")
    st.dataframe(result.room_metrics, width="stretch", hide_index=True)

    assignment_csv = ledger.to_csv(index=False).encode("utf-8-sig")
    room_csv = result.room_metrics.to_csv(index=False).encode("utf-8-sig")
    metadata_json = json.dumps(
        result.metadata(),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    download1, download2, download3 = st.columns(3)
    download1.download_button(
        "Download assignments",
        assignment_csv,
        "unimate_assignments.csv",
        "text/csv",
        width="stretch",
    )
    download2.download_button(
        "Download room metrics",
        room_csv,
        "unimate_room_metrics.csv",
        "text/csv",
        width="stretch",
    )
    download3.download_button(
        "Download run metadata",
        metadata_json,
        "unimate_run_metadata.json",
        "application/json",
        width="stretch",
    )


def main() -> None:
    st.set_page_config(
        page_title="UniMate Room Assignment",
        layout="wide",
    )
    st.title("UniMate Room Assignment")
    st.caption(
        "Validated multi-criteria optimization for university dormitories. "
        "Sensitive demographic fields are excluded from compatibility scoring."
    )

    raw, source_name = load_dataset()
    optimization_config, scoring_config = optimization_controls()
    if raw.empty:
        st.info("Upload an original questionnaire CSV or Excel file to begin.")
        return

    st.caption(f"Data source: {source_name}")
    parsed = parse_student_survey(raw)
    render_validation(parsed)
    if not parsed.is_valid:
        st.error("Correct the validation errors before running an assignment.")
        return

    raw_hash = hashlib.sha256(
        pd.util.hash_pandas_object(raw.astype(str), index=False).to_numpy().tobytes()
    ).hexdigest()
    session_key = (
        raw_hash,
        optimization_config.fingerprint(),
        scoring_config.fingerprint(),
    )
    if st.session_state.get("result_session_key") != session_key:
        st.session_state.pop("optimization_result", None)
        st.session_state.pop("normalized_students", None)

    with st.expander("Normalized data preview"):
        safe_preview_fields = [
            field
            for field in parsed.data.columns
            if field not in {"residence", "ethnicity", "cultural_group"}
        ]
        st.dataframe(
            parsed.data[safe_preview_fields].head(200),
            width="stretch",
        )

    if st.button(
        "Run room assignment",
        type="primary",
        width="stretch",
    ):
        progress = st.progress(0.0, text="Computing compatibility scores")
        scorer = CompatibilityScorer(scoring_config)
        scores = scorer.score(parsed.data)
        progress.progress(0.1, text="Building initial balanced assignments")
        seen_events = 0

        def update_progress(event: dict) -> None:
            nonlocal seen_events
            seen_events += 1
            phase = str(event.get("phase", "search"))
            fraction = min(0.95, 0.1 + seen_events * 0.03)
            progress.progress(
                fraction,
                text=(
                    f"{phase}: worst={event.get('min_student_utility', 0):.1f}, "
                    f"p10={event.get('p10_room_quality', 0):.1f}"
                ),
            )

        optimizer = RoomOptimizer(optimization_config)
        result = optimizer.optimize(
            parsed.data,
            scores,
            progress_callback=update_progress,
        )
        progress.progress(1.0, text="Assignment complete")
        st.session_state["optimization_result"] = result
        st.session_state["normalized_students"] = parsed.data
        st.session_state["result_session_key"] = session_key

    result = st.session_state.get("optimization_result")
    result_students = st.session_state.get("normalized_students")
    if result is not None and result_students is not None:
        render_results(result, result_students)


if __name__ == "__main__":
    main()
