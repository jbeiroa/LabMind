import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from metaflow import FlowSpec, Parameter, current, step, project

from selection.contracts import (
    AutoRangesFile,
    RangeEntry,
    ReviewManifest,
    SelectionMetrics,
    SelectionRangesFile,
    build_review_paths,
    compute_auto_ranges_hash,
    validate_selection_file,
)
from selection.detectors import (
    annotate_reasons,
    combine_flags,
    compute_jump_flags,
    compute_mad_flags,
    compute_physical_bound_flags,
)
from selection.ranges import (
    apply_keep_ranges,
    complement_keep_ranges,
    flags_to_ranges,
    merge_adjacent_ranges,
    normalize_keep_ranges,
)


class DataSelectorFlow(FlowSpec):
    # Core params
    input_parquet = Parameter(
        "input-parquet", help="Path to input parquet file", default=""
    )
    auto_only = Parameter(
        "auto-only", help="Skip human review and use auto ranges", type=bool, default=True
    )
    dry_run = Parameter(
        "dry-run", help="Run detection and exit after emitting bundle", type=bool, default=False
    )
    
    # Metadata params
    experiment_id = Parameter("experiment-id", default="exp_default")
    trial_id = Parameter("trial-id", default="t01")
    sensor_id = Parameter("sensor-id", default="HC-SR04")
    
    # Strategy params
    min_value = Parameter("min-value", type=float, default=2.0)
    max_value = Parameter("max-value", type=float, default=400.0)
    max_abs_jump = Parameter("max-abs-jump", type=float, default=20.0)
    mad_z_threshold = Parameter("mad-z-threshold", type=float, default=3.5)
    rolling_window = Parameter("rolling-window", type=int, default=21)
    
    # Range params
    merge_gap_ms = Parameter("merge-gap-ms", type=int, default=100)
    min_segment_len_ms = Parameter("min-segment-len-ms", type=int, default=50)

    # Output params
    output_dir = Parameter("output-dir", default="data/selected")
    review_dir = Parameter("review-dir", default="data/review")

    @step
    def start(self):
        self.started_at = datetime.now(UTC)
        self.run_id = current.run_id
        
        # In a real scenario, we'd initialize MLflow here
        # import mlflow
        # mlflow.set_experiment("LabMind_Selection")
        # self.mlflow_run_id = mlflow.start_run().info.run_id
        
        if not self.input_parquet:
            raise ValueError("--input-parquet is required")
            
        self.next(self.load_data)

    @step
    def load_data(self):
        path = Path(self.input_parquet)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
            
        self.df = pd.read_parquet(path)
        self.rows_in = len(self.df)
        self.data_start_ts = int(self.df["timestamp_ms"].min())
        self.data_end_ts = int(self.df["timestamp_ms"].max())
        
        self.next(self.auto_detect)

    @step
    def auto_detect(self):
        # 1. Run detectors
        bound_flags = compute_physical_bound_flags(self.df, self.min_value, self.max_value)
        jump_flags = compute_jump_flags(self.df, self.max_abs_jump)
        mad_flags, mad_scores = compute_mad_flags(
            self.df, self.rolling_window, self.mad_z_threshold
        )
        
        # 2. Annotate DF
        self.df["is_anomaly"] = combine_flags(bound_flags, jump_flags, mad_flags)
        self.df["anomaly_score"] = mad_scores
        self.df["reason_codes"] = annotate_reasons(
            self.df, bound_flags, jump_flags, mad_flags
        )
        
        # 3. Build anomaly ranges
        anomaly_ranges = []
        anomaly_ranges.extend(flags_to_ranges(self.df["timestamp_ms"], bound_flags, "PHYSICAL_BOUND"))
        anomaly_ranges.extend(flags_to_ranges(self.df["timestamp_ms"], jump_flags, "JUMP"))
        anomaly_ranges.extend(flags_to_ranges(self.df["timestamp_ms"], mad_flags, "OUTLIER_MAD"))
        
        # 4. Merge and finalize auto ranges
        self.merged_anomalies = merge_adjacent_ranges(
            anomaly_ranges, self.merge_gap_ms, self.min_segment_len_ms
        )
        
        # 5. Compute auto keep ranges
        self.auto_keep_ranges = complement_keep_ranges(
            self.data_start_ts, self.data_end_ts, self.merged_anomalies
        )
        
        self.next(self.emit_review_bundle)

    @step
    def emit_review_bundle(self):
        paths = build_review_paths(
            self.review_dir, self.experiment_id, self.trial_id, self.run_id
        )
        paths["root"].mkdir(parents=True, exist_ok=True)
        
        # Save review data
        self.df.to_parquet(paths["data"], index=False)
        self.review_data_path = str(paths["data"])
        
        # Save auto ranges
        auto_ranges_data = AutoRangesFile(
            experiment_id=self.experiment_id,
            trial_id=self.trial_id,
            sensor_id=self.sensor_id,
            ranges=[RangeEntry(**r) for r in self.merged_anomalies]
        )
        with open(paths["auto_ranges"], "w") as f:
            f.write(auto_ranges_data.model_dump_json(indent=2))
        self.auto_ranges_path = str(paths["auto_ranges"])
        
        # Compute hash
        self.auto_ranges_hash = compute_auto_ranges_hash(auto_ranges_data.model_dump())
        
        # Save manifest
        manifest = ReviewManifest(
            experiment_id=self.experiment_id,
            trial_id=self.trial_id,
            sensor_id=self.sensor_id,
            run_id=self.run_id,
            review_data_path=self.review_data_path,
            auto_ranges_path=self.auto_ranges_path,
            auto_ranges_hash=self.auto_ranges_hash
        )
        with open(paths["manifest"], "w") as f:
            f.write(manifest.model_dump_json(indent=2))
        self.manifest_path = str(paths["manifest"])
        
        print(f"Review bundle emitted at: {paths['root']}")
        self.branch_name = "dry" if self.dry_run else "normal"
        self.next(self.check_dry_run_switch)

    @step
    def check_dry_run_switch(self):
        self.next({"dry": self.end, "normal": self.resolve_selection}, condition="branch_name")

    @step
    def resolve_selection(self):
        if self.auto_only:
            self.final_keep_ranges = self.auto_keep_ranges
            self.selection_mode = "auto"
        else:
            # In a real scenario, we'd wait for a file to appear or use a signal
            # For now, we look for the selection file defined by the contract
            paths = build_review_paths(
                self.review_dir, self.experiment_id, self.trial_id, self.run_id
            )
            selection_path = paths["selection"]
            
            if not selection_path.exists():
                raise RuntimeError(
                    f"Selection file not found at {selection_path}. "
                    "Please run the review app and save your selection."
                )
            
            with open(selection_path, "r") as f:
                selection_data = SelectionRangesFile.model_validate_json(f.read())
            
            # Load manifest for validation
            with open(self.manifest_path, "r") as f:
                manifest = ReviewManifest.model_validate_json(f.read())
                
            validate_selection_file(
                selection_data, manifest, self.data_start_ts, self.data_end_ts
            )
            
            self.final_keep_ranges = selection_data.selected_keep_ranges
            self.selection_mode = "manual"
            
        self.next(self.materialize_selected)

    @step
    def materialize_selected(self):
        # 1. Normalize
        self.final_keep_ranges = normalize_keep_ranges(self.final_keep_ranges)
        
        # 2. Apply
        self.selected_df = apply_keep_ranges(self.df, self.final_keep_ranges)
        self.rows_selected = len(self.selected_df)
        self.pct_selected = (self.rows_selected / self.rows_in) * 100 if self.rows_in > 0 else 0
        
        # 3. Persist
        output_path = (
            Path(self.output_dir) 
            / self.experiment_id 
            / self.trial_id 
            / f"selected-{self.run_id}.parquet"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.selected_df.to_parquet(output_path, index=False)
        self.selected_parquet_path = str(output_path)
        
        # 4. Metrics
        self.metrics = SelectionMetrics(
            rows_in=self.rows_in,
            rows_selected=self.rows_selected,
            pct_selected=self.pct_selected,
            manual_edit_count=0 if self.auto_only else 1, # Simple placeholder
            num_auto_ranges=len(self.auto_keep_ranges),
            num_final_ranges=len(self.final_keep_ranges)
        )
        
        metrics_path = output_path.with_suffix(".metrics.json")
        with open(metrics_path, "w") as f:
            f.write(self.metrics.model_dump_json(indent=2))
            
        print(f"Materialized {self.rows_selected} rows to {self.selected_parquet_path}")
        self.next(self.end)

    @step
    def end(self):
        if not self.dry_run:
            print(f"Selection complete. Mode: {self.selection_mode}. Rows: {self.rows_selected}")
        else:
            print("Dry run complete.")


if __name__ == "__main__":
    DataSelectorFlow()
