import os
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# Import your new optimized engine components
from engine.preprocessing import preprocess_student_data
from engine import CompatibilityEngine, DormOptimizationEngine


def load_dataset() -> pd.DataFrame:
    """Load dataset from user upload or fall back to default path."""
    st.sidebar.subheader("📅 Data Source Ingestion")
    uploaded = st.sidebar.file_uploader("Upload Student Registration Data", type=["csv", "xlsx"])
    
    if uploaded is not None:
        if uploaded.name.endswith('.xlsx'):
            return pd.read_excel(uploaded)
        return pd.read_csv(uploaded)
        
    # Fallback to default path
    default_csv = os.path.join(os.getcwd(), "Data", "EncodedWomen_english.csv")
    if os.path.exists(default_csv):
        return pd.read_csv(default_csv)
        
    st.sidebar.warning("Waiting for student database upload...")
    return pd.DataFrame()


def sidebar_optimization_controls() -> dict:
    """Render weights and constraint limits to control optimization search."""
    st.sidebar.title("🎛️ Optimization Parameters")
    st.sidebar.caption("Fine-tune compatibility balancing metrics")

    st.sidebar.subheader("Pairwise Scoring Weights")
    w_clean = st.sidebar.slider("Cleanliness Alignment", 0, 100, 50, help="Weight for matching tidy vs relaxed room-habits")
    w_noise = st.sidebar.slider("Noise & Atmosphere Alignment", 0, 100, 40)
    w_study = st.sidebar.slider("Quiet Study Preference", 0, 100, 40)
    w_schedule = st.sidebar.slider("Sleep/Wake Timeline Matching", 0, 100, 30)

    st.sidebar.markdown("---")
    st.sidebar.subheader("Room Physical Constraints")
    capacity = st.sidebar.number_input("Max Target Room Capacity", min_value=2, max_value=8, value=2, step=1)
    solver_timeout = st.sidebar.number_input("Solver Timeout (Seconds)", min_value=5, max_value=300, value=30)

    return {
        "weights": {
            "cleanliness": w_clean,
            "noise": w_noise,
            "study": w_study,
            "schedule": w_schedule
        },
        "capacity": int(capacity),
        "timeout": int(solver_timeout)
    }


def calculate_assignment_analytics(assigned_df: pd.DataFrame, matrix: np.ndarray) -> dict:
    """Calculates granular optimization performance evaluations across allocations."""
    room_scores = []
    for _, group in assigned_df.groupby("room_id"):
        idxs = group["student_idx"].tolist()
        if len(idxs) < 2:
            room_scores.append(0)
            continue
        
        # Calculate intra-room compatibility edges sum
        pair_scores = []
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                pair_scores.append(matrix[idxs[i]][idxs[j]])
        room_scores.append(np.mean(pair_scores))

    return {
        "avg_compat": float(np.mean(room_scores)),
        "min_compat": float(np.min(room_scores)),
        "room_scores": room_scores
    }


def main():
    st.set_page_config(page_title="UniMate | Optimization Engine", layout="wide", page_icon="🛏️")
    st.title("🛏️ UniMate: Advanced Constrained Room Optimization Engine")
    st.caption("Mathematical allocation platform replacing legacy heuristic models with exact constraint programming solver models.")

    # Ingest Raw Data
    raw_df = load_dataset()
    
    if raw_df.empty:
        st.info("👋 Welcome! Please upload your student registration Excel or CSV sheet in the sidebar menu to begin calculation.")
        return

    # Gather Engine Adjustments from Sidebar Controls
    controls = sidebar_optimization_controls()
    
    st.markdown("---")
    
    # 1. Preprocessing Stage execution
    with st.spinner("Processing data strings into relational category mappings..."):
        try:
            processed_df = preprocess_student_data(raw_df)
        except Exception as e:
            st.error(f"Data mapping transformation failure: {e}. Check if column structures match expectations.")
            return

    # Performance Counters & Metadata Overview
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Candidates Ingested", f"{len(processed_df)} Students")
    with col2:
        target_rooms_needed = int(np.ceil(len(processed_df) / controls["capacity"]))
        st.metric("Required Target Dormitories", f"{target_rooms_needed} Rooms")
    with col3:
        st.metric("Constraint Architecture", "OR-Tools CP-SAT Model")

    # 2. Setup Rooms Configuration Engine
    rooms_df = pd.DataFrame([
        {"room_id": r, "room_name": f"Dormitory Room {r:03d}", "capacity": controls["capacity"]}
        for r in range(1, target_rooms_needed + 1)
    ])

    # Run Optimization Core trigger block
    st.subheader("Operational Controls Execution")
    if st.button("Execute Mathematical Optimization Plan", type="primary", use_container_width=True):
        
        # Step A: Graph edge scores compilation
        with st.spinner("Compiling cross-compatibility matrix maps across cohorts..."):
            scorer = CompatibilityEngine(weights=controls["weights"])
            matrix = scorer.compute_matrix(processed_df)
            st.toast("Compatibility graph fully generated.", icon="📊")

        # Step B: Trigger CP-SAT Solver Instance with Progress Tracking
        progress_placeholder = st.empty()
        
        # Progress tracking state
        progress_state = {
            "best_objective": 0,
            "best_bound": 0,
            "solution_count": 0
        }
        
        def update_progress(current_objective, best_bound, solution_count, gap_percent):
            """Callback function to update UI during optimization."""
            progress_state["best_objective"] = current_objective
            progress_state["best_bound"] = best_bound
            progress_state["solution_count"] = solution_count
            
            # Update progress display
            with progress_placeholder.container():
                st.info(f"🔄 Optimization in progress... Found {solution_count} solution(s)")
                col_prog1, col_prog2, col_prog3 = st.columns(3)
                with col_prog1:
                    st.metric("Current Best Compatibility Score", f"{int(current_objective):,}")
                with col_prog2:
                    st.metric("Theoretical Upper Bound", f"{int(best_bound):,}")
                with col_prog3:
                    st.metric("Optimality Gap", f"{gap_percent:.1f}%")
        
        with st.spinner(f"Running Google OR-Tools branch-and-bound optimization (Timeout: {controls['timeout']}s)..."):
            engine = DormOptimizationEngine(processed_df, rooms_df, matrix)
            engine.build_model()
            engine.set_progress_callback(update_progress)  # Set progress callback
            results_df, status = engine.solve(time_limit_sec=controls["timeout"])

        if results_df is not None:
            # Clear progress placeholder
            progress_placeholder.empty()
            
            st.balloons()
            st.success(f"Optimal Allocation Plan Discovered Successfully. Mathematical Bound State: **{status}**")
            
            # Merge details to append diagnostic values
            assigned_master = results_df.merge(processed_df, on="student_id")
            analytics = calculate_assignment_analytics(assigned_master, matrix)
            
            # Print performance metrics
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Global Mean Room Compatibility Index", f"{analytics['avg_compat']:.2f} pts")
            with m2:
                st.metric("Worst-Case Room Compatibility Floor", f"{analytics['min_compat']:.2f} pts")

            # Chart Analytics Plot
            st.subheader("📊 Engine Outcome Evaluation Metrics")
            fig = px.histogram(
                x=analytics['room_scores'], 
                nbins=10, 
                labels={'x': 'Average Compatibility Score Within Room'},
                title="Global Room Quality Allocation Distribution Variance",
                color_discrete_sequence=['#2E7D32']
            )
            st.plotly_chart(fig, use_container_width=True)

            # Explainable Breakdown tables
            st.subheader("📋 Final Optimized Assignments Matrix Ledger")
            
            # Format clean view for users
            display_ledger = assigned_master[[
                "room_name", "student_id", "faculty", "major", 
                "sleep_window", "wake_window", "cleanliness", "cultural_group"
            ]].copy()
            
            # Replace numeric labels for readable tracking tables
            display_ledger['cleanliness'] = display_ledger['cleanliness'].map({1: 'Tidy Seekers', 0: 'Relaxed'})
            
            st.dataframe(display_ledger.sort_values(by="room_name"), use_container_width=True)

            # Export Pipeline
            csv_data = display_ledger.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Optimal Housing Layout Strategy (CSV)",
                data=csv_data,
                file_name="unimate_optimal_housing_manifest.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            progress_placeholder.empty()
            st.error("Solver Error: A valid arrangement is mathematically impossible under these parameter boundaries.")
            st.info("Try increasing Room Capacity or adjusting structural settings to expand search windows.")
            
    else:
        st.info("💡 Click the button above to execute your multi-attribute placement matrix optimization routines.")


if __name__ == "__main__":
    main()