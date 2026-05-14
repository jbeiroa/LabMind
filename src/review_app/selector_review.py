import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from selection.contracts import (
    AutoRangesFile,
    ReviewManifest,
    SelectionRangesFile,
)


def load_manifest(manifest_path: Path) -> ReviewManifest:
    with open(manifest_path, "r") as f:
        return ReviewManifest.model_validate_json(f.read())


def load_auto_ranges(auto_ranges_path: Path) -> AutoRangesFile:
    with open(auto_ranges_path, "r") as f:
        return AutoRangesFile.model_validate_json(f.read())


def main():
    st.set_page_config(layout="wide", page_title="LabMind Data Selector Review")
    st.title("🔍 LabMind Data Selector Review")

    # 1. Sidebar - Load Manifest
    st.sidebar.header("Configuration")
    manifest_path_str = st.sidebar.text_input(
        "Manifest Path", value="data/review/exp_default/t01/local/review_manifest.json"
    )

    if not manifest_path_str:
        st.info("Please provide a path to a review manifest.")
        return

    manifest_path = Path(manifest_path_str)
    if not manifest_path.exists():
        st.error(f"Manifest not found: {manifest_path}")
        return

    try:
        manifest = load_manifest(manifest_path)
        auto_ranges = load_auto_ranges(Path(manifest.auto_ranges_path))
    except Exception as e:
        st.error(f"Error loading manifest/ranges: {e}")
        return

    st.sidebar.success("Manifest Loaded")
    st.sidebar.json(manifest.model_dump())

    # 2. Data Loading
    df = pd.read_parquet(manifest.review_data_path)
    
    # 3. Range Management
    if "keep_ranges" not in st.session_state:
        # Initialize with complement of anomalies (auto keep ranges)
        # Note: In a real app, we'd compute this or load from flow artifact.
        # For simplicity in the UI, let's just use the anomaly ranges and allow deleting them.
        st.session_state.anomaly_ranges = [
            {"start": r.start_ts_ms, "end": r.end_ts_ms, "label": r.label}
            for r in auto_ranges.ranges
        ]

    # 4. Visualization
    st.header("Measurement Visualization")
    
    fig = go.Figure()
    
    # Raw Data
    fig.add_trace(go.Scatter(
        x=df["timestamp_ms"], 
        y=df["value"], 
        mode='lines+markers',
        name='Measurements',
        line=dict(color='blue')
    ))
    
    # Anomaly Points
    anomalies = df[df["is_anomaly"]]
    if not anomalies.empty:
        fig.add_trace(go.Scatter(
            x=anomalies["timestamp_ms"],
            y=anomalies["value"],
            mode='markers',
            name='Anomaly Points',
            marker=dict(color='red', size=8, symbol='x')
        ))

    # Anomaly Ranges (Shaded Areas)
    for r in st.session_state.anomaly_ranges:
        fig.add_vrect(
            x0=r["start"], x1=r["end"],
            fillcolor="red", opacity=0.2,
            layer="below", line_width=0,
            annotation_text=r["label"], annotation_position="top left"
        )

    fig.update_layout(
        xaxis_title="Timestamp (ms)",
        yaxis_title="Value",
        height=600,
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # 5. Manual Overrides
    st.header("Selection Overrides")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Auto-detected Anomalies")
        for i, r in enumerate(st.session_state.anomaly_ranges):
            cols = st.columns([3, 1])
            cols[0].write(f"**{r['label']}**: {r['start']} - {r['end']}")
            if cols[1].button("Remove", key=f"remove_{i}"):
                st.session_state.anomaly_ranges.pop(i)
                st.rerun()

    with col2:
        st.subheader("Add Custom Anomaly Range")
        with st.form("add_range"):
            new_start = st.number_input("Start TS (ms)", value=int(df["timestamp_ms"].min()))
            new_end = st.number_input("End TS (ms)", value=int(df["timestamp_ms"].max()))
            new_label = st.text_input("Label", value="MANUAL")
            if st.form_submit_button("Add Range"):
                st.session_state.anomaly_ranges.append({
                    "start": new_start, "end": new_end, "label": new_label
                })
                st.rerun()

    # 6. Save Selection
    st.header("Finalize Selection")
    
    if st.button("💾 Save Selection & Approve"):
        # Convert anomaly ranges back to keep ranges
        from selection.ranges import complement_keep_ranges
        
        anomaly_list = [
            {"start_ts_ms": r["start"], "end_ts_ms": r["end"]}
            for r in st.session_state.anomaly_ranges
        ]
        
        keep_ranges = complement_keep_ranges(
            int(df["timestamp_ms"].min()),
            int(df["timestamp_ms"].max()),
            anomaly_list
        )
        
        selection = SelectionRangesFile(
            experiment_id=manifest.experiment_id,
            trial_id=manifest.trial_id,
            sensor_id=manifest.sensor_id,
            selected_keep_ranges=keep_ranges,
            base_auto_ranges_hash=manifest.auto_ranges_hash,
            reviewer_id="human_user",
            notes="Reviewed via Streamlit App"
        )
        
        save_path = Path(manifest.auto_ranges_path).parent / "selection_ranges.json"
        with open(save_path, "w") as f:
            f.write(selection.model_dump_json(indent=2))
            
        st.success(f"Selection saved to: {save_path}")
        st.info("You can now resume the Metaflow run.")


if __name__ == "__main__":
    main()
