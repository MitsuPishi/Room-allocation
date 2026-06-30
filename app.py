"""Streamlit interface for the validated UniMate optimization engine."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

import numpy as np
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
TABLE_HEIGHT = 420
PROFILE_FIELDS = (
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
CONTRIBUTION_COLUMNS = (
    "cleanliness_contribution",
    "noise_contribution",
    "study_contribution",
    "schedule_contribution",
)
SENSITIVE_FIELDS = {"residence", "ethnicity", "cultural_group"}


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

    st.sidebar.subheader("Advanced optimizer")
    cp_sat_supported = sys.version_info < (3, 14)
    cp_sat_enabled = st.sidebar.checkbox(
        "CP-SAT neighborhood refinement",
        value=cp_sat_supported,
        disabled=not cp_sat_supported,
        help=(
            "Optional late-stage OR-Tools refinement. It is disabled on Python "
            "3.14 because the installed OR-Tools build can terminate the Python "
            "process during this phase."
        ),
    )
    if not cp_sat_supported:
        st.sidebar.warning(
            "Python 3.14 detected: CP-SAT refinement is disabled to prevent the "
            "dashboard from stopping during optimization. Python 3.12 is the "
            "supported runtime for full optimization."
        )

    optimization = OptimizationConfig(
        capacity=int(capacity),
        time_limit_seconds=float(time_limit),
        seed=int(seed),
        cp_sat_neighborhood_rooms=4 if cp_sat_enabled else 0,
    )
    return optimization, scoring


def clean_label(value: Any) -> str:
    if pd.isna(value):
        return "Blank"
    return str(value)


def numeric_range(series: pd.Series) -> tuple[float, float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return 0.0, 0.0
    minimum = float(values.min())
    maximum = float(values.max())
    if np.isclose(minimum, maximum):
        maximum = minimum + 1.0
    return minimum, maximum


def safe_multiselect(
    label: str,
    values: pd.Series,
    *,
    key: str,
    max_options: int = 80,
) -> list[Any]:
    options = sorted(
        [value for value in values.dropna().unique().tolist()],
        key=lambda value: str(value),
    )
    if len(options) > max_options:
        st.caption(f"{label}: too many unique values for a compact filter.")
        return []
    return st.multiselect(label, options=options, format_func=clean_label, key=key)


def build_assignment_ledger(result, students: pd.DataFrame) -> pd.DataFrame:
    profile_fields = [field for field in PROFILE_FIELDS if field in students.columns]
    return result.assignments.merge(
        students[profile_fields],
        on="student_idx",
        how="left",
    )


def search_history_frame(result) -> pd.DataFrame:
    if not result.search_history:
        return pd.DataFrame()
    history = pd.DataFrame(result.search_history)
    if "iteration" not in history.columns:
        history["iteration"] = np.nan
    history.insert(0, "step", np.arange(1, len(history) + 1))
    return history


def contribution_columns(room_metrics: pd.DataFrame) -> list[str]:
    return [column for column in CONTRIBUTION_COLUMNS if column in room_metrics.columns]


def contribution_labels(columns: list[str]) -> list[str]:
    return [
        column.replace("_contribution", "").replace("_", " ").title()
        for column in columns
    ]


def room_roster(ledger: pd.DataFrame, room_id: str) -> pd.DataFrame:
    return ledger.loc[ledger["room_id"] == room_id].sort_values("bed")


def filter_by_query(data: pd.DataFrame, columns: list[str], query: str) -> pd.DataFrame:
    query = query.strip().lower()
    if not query:
        return data
    available = [column for column in columns if column in data.columns]
    if not available:
        return data
    mask = pd.Series(False, index=data.index)
    for column in available:
        mask |= data[column].fillna("").astype(str).str.lower().str.contains(
            query,
            regex=False,
        )
    return data.loc[mask]


def metric_cards(result) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Worst student utility", f"{result.metrics.min_student_utility:.1f}")
    col2.metric("10th percentile room", f"{result.metrics.p10_room_quality:.1f}")
    col3.metric("Mean student utility", f"{result.metrics.mean_student_utility:.1f}")
    col4.metric("Runtime", f"{result.runtime_seconds:.1f}s")


def render_validation(parsed) -> None:
    left, middle, right = st.columns(3)
    left.metric("Students", f"{len(parsed.data):,}")
    middle.metric("Validation errors", parsed.error_count)
    right.metric("Validation warnings", parsed.warning_count)
    if parsed.issues:
        with st.expander("Validation report", expanded=not parsed.is_valid):
            st.dataframe(parsed.validation_report(), width="stretch")


def render_overview(result, ledger: pd.DataFrame) -> None:
    metric_cards(result)

    left, right = st.columns(2)
    with left:
        figure = px.histogram(
            result.room_metrics,
            x="room_quality",
            nbins=24,
            title="Room quality distribution",
            labels={"room_quality": "Weakest-student utility"},
        )
        st.plotly_chart(figure, width="stretch")
    with right:
        figure = px.histogram(
            ledger,
            x="student_utility",
            nbins=24,
            title="Student utility distribution",
            labels={"student_utility": "Student utility"},
        )
        st.plotly_chart(figure, width="stretch")

    history = search_history_frame(result)
    left, right = st.columns(2)
    with left:
        if history.empty:
            st.info("No optimization history was recorded for this run.")
        else:
            metric_columns = [
                column
                for column in (
                    "min_student_utility",
                    "p10_room_quality",
                    "mean_student_utility",
                )
                if column in history.columns
            ]
            history_long = history.melt(
                id_vars=["step"],
                value_vars=metric_columns,
                var_name="metric",
                value_name="value",
            )
            figure = px.line(
                history_long,
                x="step",
                y="value",
                color="metric",
                markers=True,
                title="Search progress",
                labels={"step": "Progress event", "value": "Utility"},
            )
            st.plotly_chart(figure, width="stretch")
    with right:
        columns = contribution_columns(result.room_metrics)
        if columns:
            averages = result.room_metrics[columns].mean().reset_index()
            averages.columns = ["criterion", "mean_contribution"]
            averages["criterion"] = contribution_labels(columns)
            figure = px.bar(
                averages,
                x="criterion",
                y="mean_contribution",
                title="Average contribution by criterion",
                labels={
                    "criterion": "Criterion",
                    "mean_contribution": "Mean room contribution",
                },
            )
            st.plotly_chart(figure, width="stretch")

    st.subheader("Lowest quality rooms")
    weakest = result.room_metrics.nsmallest(12, "room_quality")
    st.dataframe(weakest, width="stretch", hide_index=True, height=TABLE_HEIGHT)


def render_room_heatmap(roster: pd.DataFrame, scores) -> None:
    indices = roster["student_idx"].astype(int).tolist()
    labels = [
        f"{row.student_name} ({row.student_id})"
        for row in roster[["student_name", "student_id"]].itertuples(index=False)
    ]
    matrix = scores.matrix[np.ix_(indices, indices)].astype(float)
    np.fill_diagonal(matrix, np.nan)
    figure = px.imshow(
        matrix,
        x=labels,
        y=labels,
        color_continuous_scale="Viridis",
        aspect="auto",
        title="Room pairwise compatibility",
        labels={"color": "Score"},
    )
    figure.update_layout(height=min(560, max(360, 52 * len(indices))))
    st.plotly_chart(figure, width="stretch")


def render_profile_mix(roster: pd.DataFrame) -> None:
    mix_fields = [
        field
        for field in (
            "faculty",
            "major",
            "sleep_window",
            "wake_window",
            "noise_tolerance",
            "study_habit",
            "cleanliness",
        )
        if field in roster.columns
    ]
    if not mix_fields:
        return
    columns = st.columns(min(3, len(mix_fields)))
    for index, field in enumerate(mix_fields):
        counts = (
            roster[field]
            .fillna("Blank")
            .astype(str)
            .value_counts()
            .rename_axis(field)
            .reset_index(name="count")
        )
        with columns[index % len(columns)]:
            figure = px.bar(
                counts,
                x=field,
                y="count",
                title=field.replace("_", " ").title(),
            )
            figure.update_layout(height=240, margin=dict(l=10, r=10, t=50, b=30))
            st.plotly_chart(figure, width="stretch")


def render_rooms_tab(result, ledger: pd.DataFrame, scores) -> pd.DataFrame:
    room_metrics = result.room_metrics.copy()
    filters, table = st.columns([1, 2])
    with filters:
        st.subheader("Room Search")
        query = st.text_input("Room id contains", key="room_query")
        quality_min, quality_max = numeric_range(room_metrics["room_quality"])
        quality_range = st.slider(
            "Room quality range",
            min_value=quality_min,
            max_value=quality_max,
            value=(quality_min, quality_max),
            step=0.1,
            key="room_quality_range",
        )
        mean_min, mean_max = numeric_range(room_metrics["mean_student_utility"])
        mean_range = st.slider(
            "Mean utility range",
            min_value=mean_min,
            max_value=mean_max,
            value=(mean_min, mean_max),
            step=0.1,
            key="room_mean_range",
        )
        size_options = sorted(room_metrics["room_size"].dropna().unique().tolist())
        selected_sizes = st.multiselect(
            "Room size",
            options=size_options,
            default=size_options,
            key="room_size_filter",
        )
        weakest_first = st.checkbox("Show weakest rooms first", value=True)

    filtered = filter_by_query(room_metrics, ["room_id"], query)
    filtered = filtered.loc[
        filtered["room_quality"].between(*quality_range)
        & filtered["mean_student_utility"].between(*mean_range)
    ]
    if selected_sizes:
        filtered = filtered.loc[filtered["room_size"].isin(selected_sizes)]
    filtered = filtered.sort_values(
        "room_quality" if weakest_first else "room_id",
        ascending=weakest_first,
    )

    with table:
        st.subheader("Rooms")
        st.caption(f"{len(filtered):,} of {len(room_metrics):,} rooms shown")
        st.dataframe(
            filtered,
            width="stretch",
            hide_index=True,
            height=TABLE_HEIGHT,
        )

    if filtered.empty:
        st.info("No rooms match the active filters.")
        return filtered

    room_options = filtered["room_id"].tolist()
    selected_room = st.selectbox(
        "Inspect room",
        options=room_options,
        key="selected_room",
    )
    roster = room_roster(ledger, selected_room)
    room_row = result.room_metrics.loc[
        result.room_metrics["room_id"] == selected_room
    ].iloc[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Room quality", f"{room_row['room_quality']:.1f}")
    col2.metric("Mean utility", f"{room_row['mean_student_utility']:.1f}")
    col3.metric("Students", f"{int(room_row['room_size'])}")

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Roster")
        st.dataframe(roster, width="stretch", hide_index=True, height=260)
    with right:
        columns = contribution_columns(result.room_metrics)
        if columns:
            values = pd.DataFrame(
                {
                    "criterion": contribution_labels(columns),
                    "contribution": [float(room_row[column]) for column in columns],
                }
            )
            figure = px.bar(
                values,
                x="criterion",
                y="contribution",
                title="Compatibility contributions",
            )
            st.plotly_chart(figure, width="stretch")

    st.subheader("Profile mix")
    render_profile_mix(roster)
    render_room_heatmap(roster, scores)
    return filtered


def render_students_tab(ledger: pd.DataFrame) -> pd.DataFrame:
    filters, table = st.columns([1, 2])
    with filters:
        st.subheader("Student Search")
        query = st.text_input("Search students", key="student_query")
        utility_min, utility_max = numeric_range(ledger["student_utility"])
        utility_range = st.slider(
            "Student utility range",
            min_value=utility_min,
            max_value=utility_max,
            value=(utility_min, utility_max),
            step=0.1,
            key="student_utility_range",
        )
        room_ids = safe_multiselect("Room id", ledger["room_id"], key="student_rooms")
        faculties = safe_multiselect("Faculty", ledger["faculty"], key="student_faculty")
        majors = safe_multiselect("Major", ledger["major"], key="student_major")
        lifestyle_filters = {}
        for field in (
            "sleep_window",
            "wake_window",
            "noise_tolerance",
            "study_habit",
            "cleanliness",
        ):
            if field in ledger.columns:
                lifestyle_filters[field] = safe_multiselect(
                    field.replace("_", " ").title(),
                    ledger[field],
                    key=f"student_{field}",
                )
        lowest_only = st.checkbox("Show lowest-utility students first", value=True)

    filtered = filter_by_query(
        ledger,
        ["student_id", "student_name", "room_id", "faculty", "major"],
        query,
    )
    filtered = filtered.loc[filtered["student_utility"].between(*utility_range)]
    if room_ids:
        filtered = filtered.loc[filtered["room_id"].isin(room_ids)]
    if faculties:
        filtered = filtered.loc[filtered["faculty"].isin(faculties)]
    if majors:
        filtered = filtered.loc[filtered["major"].isin(majors)]
    for field, values in lifestyle_filters.items():
        if values:
            filtered = filtered.loc[filtered[field].isin(values)]
    filtered = filtered.sort_values(
        ["student_utility", "room_id", "bed"] if lowest_only else ["room_id", "bed"],
        ascending=True,
    )

    with table:
        st.subheader("Students")
        st.caption(f"{len(filtered):,} of {len(ledger):,} students shown")
        st.dataframe(
            filtered,
            width="stretch",
            hide_index=True,
            height=TABLE_HEIGHT,
        )
    return filtered


def pair_contribution_frame(scores, first_idx: int, second_idx: int) -> pd.DataFrame:
    contributions = scores.explain_pair(first_idx, second_idx)
    return pd.DataFrame(
        {
            "criterion": [key.replace("_", " ").title() for key in contributions],
            "score": list(contributions.values()),
        }
    )


def render_student_pair_details(
    scores,
    first_idx: int,
    second_idx: int,
    title: str,
) -> None:
    frame = pair_contribution_frame(scores, first_idx, second_idx)
    figure = px.bar(
        frame.loc[frame["criterion"] != "Total"],
        x="criterion",
        y="score",
        title=title,
        labels={"score": "Contribution"},
    )
    st.plotly_chart(figure, width="stretch")
    total = frame.loc[frame["criterion"] == "Total", "score"]
    if not total.empty:
        st.metric("Total compatibility", f"{float(total.iloc[0]):.1f}")


def render_investigate_tab(ledger: pd.DataFrame, scores) -> None:
    if ledger.empty:
        st.info("No assignment records are available to investigate.")
        return

    options = ledger.sort_values(["student_name", "student_id"]).to_dict("records")
    selected = st.selectbox(
        "Student",
        options=options,
        format_func=lambda row: (
            f"{row['student_name']} ({row['student_id']}) - {row['room_id']}"
        ),
        key="investigate_student",
    )
    selected_idx = int(selected["student_idx"])
    selected_room = selected["room_id"]
    roster = room_roster(ledger, selected_room)
    roommates = roster.loc[roster["student_idx"] != selected_idx].copy()

    col1, col2, col3 = st.columns(3)
    col1.metric("Assigned room", selected_room)
    col2.metric("Student utility", f"{float(selected['student_utility']):.1f}")
    col3.metric("Room quality", f"{float(selected['room_quality']):.1f}")

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Assigned room roster")
        st.dataframe(roster, width="stretch", hide_index=True, height=260)
    with right:
        if roommates.empty:
            st.info("This student has no roommates in the current assignment.")
        else:
            pair_rows = []
            for roommate in roommates.itertuples(index=False):
                pair_rows.append(
                    {
                        "roommate": f"{roommate.student_name} ({roommate.student_id})",
                        "compatibility": float(
                            scores.matrix[selected_idx, int(roommate.student_idx)]
                        ),
                    }
                )
            pair_frame = pd.DataFrame(pair_rows).sort_values("compatibility")
            figure = px.bar(
                pair_frame,
                x="compatibility",
                y="roommate",
                orientation="h",
                title="Roommate compatibility",
            )
            st.plotly_chart(figure, width="stretch")

    if not roommates.empty:
        roommate_options = roommates.sort_values("student_name").to_dict("records")
        selected_roommate = st.selectbox(
            "Explain assigned roommate pair",
            options=roommate_options,
            format_func=lambda row: f"{row['student_name']} ({row['student_id']})",
            key="assigned_pair",
        )
        render_student_pair_details(
            scores,
            selected_idx,
            int(selected_roommate["student_idx"]),
            "Assigned pair contribution breakdown",
        )

    st.subheader("Compatibility lookup")
    comparison_options = ledger.sort_values(["student_name", "student_id"]).to_dict(
        "records"
    )
    comparison = st.selectbox(
        "Compare with another student",
        options=comparison_options,
        format_func=lambda row: (
            f"{row['student_name']} ({row['student_id']}) - {row['room_id']}"
        ),
        key="comparison_student",
    )
    if int(comparison["student_idx"]) == selected_idx:
        st.info("Choose a different student to compare pair compatibility.")
    else:
        render_student_pair_details(
            scores,
            selected_idx,
            int(comparison["student_idx"]),
            "Selected pair contribution breakdown",
        )


def render_exports_tab(
    result,
    ledger: pd.DataFrame,
    filtered_rooms: pd.DataFrame,
    filtered_students: pd.DataFrame,
) -> None:
    st.subheader("Full run exports")
    assignment_csv = ledger.to_csv(index=False).encode("utf-8-sig")
    room_csv = result.room_metrics.to_csv(index=False).encode("utf-8-sig")
    student_csv = result.student_metrics.to_csv(index=False).encode("utf-8-sig")
    metadata_json = json.dumps(
        result.metadata(),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    download1, download2, download3, download4 = st.columns(4)
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
        "Download student metrics",
        student_csv,
        "unimate_student_metrics.csv",
        "text/csv",
        width="stretch",
    )
    download4.download_button(
        "Download run metadata",
        metadata_json,
        "unimate_run_metadata.json",
        "application/json",
        width="stretch",
    )

    st.subheader("Filtered exports")
    col1, col2 = st.columns(2)
    col1.download_button(
        "Download filtered rooms",
        filtered_rooms.to_csv(index=False).encode("utf-8-sig"),
        "unimate_filtered_rooms.csv",
        "text/csv",
        width="stretch",
    )
    col2.download_button(
        "Download filtered students",
        filtered_students.to_csv(index=False).encode("utf-8-sig"),
        "unimate_filtered_students.csv",
        "text/csv",
        width="stretch",
    )


def render_results(result, students: pd.DataFrame, scores) -> None:
    st.success(
        "Assignment completed. Status: best solution found within the configured "
        "search budget; global optimality is not claimed."
    )
    ledger = build_assignment_ledger(result, students)
    view = st.radio(
        "Dashboard section",
        ["Overview", "Rooms", "Students", "Investigate", "Exports"],
        horizontal=True,
        label_visibility="collapsed",
        key="dashboard_section",
    )

    if view == "Overview":
        render_overview(result, ledger)
    elif view == "Rooms":
        filtered_rooms = render_rooms_tab(result, ledger, scores)
        st.session_state["filtered_rooms_export"] = filtered_rooms
    elif view == "Students":
        filtered_students = render_students_tab(ledger)
        st.session_state["filtered_students_export"] = filtered_students
    elif view == "Investigate":
        render_investigate_tab(ledger, scores)
    else:
        filtered_rooms = st.session_state.get(
            "filtered_rooms_export",
            result.room_metrics.copy(),
        )
        filtered_students = st.session_state.get(
            "filtered_students_export",
            ledger.copy(),
        )
        render_exports_tab(result, ledger, filtered_rooms, filtered_students)


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
        st.session_state.pop("compatibility_scores", None)

    with st.expander("Normalized data preview"):
        safe_preview_fields = [
            field
            for field in parsed.data.columns
            if field not in SENSITIVE_FIELDS
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
        st.session_state["compatibility_scores"] = scores
        st.session_state["result_session_key"] = session_key

    result = st.session_state.get("optimization_result")
    result_students = st.session_state.get("normalized_students")
    scores = st.session_state.get("compatibility_scores")
    if result is not None and result_students is not None and scores is not None:
        render_results(result, result_students, scores)


if __name__ == "__main__":
    main()
