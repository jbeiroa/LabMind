from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class RangeEntry(BaseModel):
    label: str
    start_ts_ms: int
    end_ts_ms: int
    confidence: float = 1.0
    reason_codes: Optional[List[str]] = None


class AutoRangesFile(BaseModel):
    experiment_id: str
    trial_id: str
    sensor_id: str
    ranges: List[RangeEntry]
    generated_at: datetime = Field(default_factory=datetime.now)


class ReviewManifest(BaseModel):
    experiment_id: str
    trial_id: str
    sensor_id: str
    run_id: str
    review_data_path: str
    auto_ranges_path: str
    auto_ranges_hash: str
    created_at: datetime = Field(default_factory=datetime.now)


class SelectionRangesFile(BaseModel):
    experiment_id: str
    trial_id: str
    sensor_id: str
    selected_keep_ranges: List[Tuple[int, int]]
    base_auto_ranges_hash: str
    reviewed_at: datetime = Field(default_factory=datetime.now)
    reviewer_id: Optional[str] = None
    notes: Optional[str] = None


class SelectionMetrics(BaseModel):
    rows_in: int
    rows_selected: int
    pct_selected: float
    manual_edit_count: int
    num_auto_ranges: int
    num_final_ranges: int


def build_review_paths(
    review_dir: str | Path, experiment_id: str, trial_id: str, run_id: str
) -> dict[str, Path]:
    base = Path(review_dir) / experiment_id / trial_id / run_id
    return {
        "root": base,
        "data": base / "review_data.parquet",
        "auto_ranges": base / "auto_ranges.json",
        "manifest": base / "review_manifest.json",
        "selection": base / "selection_ranges.json",
    }


def compute_auto_ranges_hash(auto_ranges_payload: dict) -> str:
    import hashlib
    import json
    from datetime import datetime

    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    # Ensure stable sort for hashing
    serialized = json.dumps(auto_ranges_payload, sort_keys=True, default=json_serial)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_selection_file(
    selection: SelectionRangesFile,
    manifest: ReviewManifest,
    data_start_ts_ms: int,
    data_end_ts_ms: int,
) -> None:
    if selection.experiment_id != manifest.experiment_id:
        raise ValueError("Experiment ID mismatch in selection file")
    if selection.trial_id != manifest.trial_id:
        raise ValueError("Trial ID mismatch in selection file")
    if selection.sensor_id != manifest.sensor_id:
        raise ValueError("Sensor ID mismatch in selection file")

    for start, end in selection.selected_keep_ranges:
        if start > end:
            raise ValueError(f"Invalid range: start ({start}) > end ({end})")
        if start < data_start_ts_ms or end > data_end_ts_ms:
            # We allow it but maybe warn? The plan says "Ranges inside data bounds"
            # Let's be strict for now as per plan.
            raise ValueError(f"Range [{start}, {end}] out of data bounds")

    # Sort check
    for i in range(len(selection.selected_keep_ranges) - 1):
        if (
            selection.selected_keep_ranges[i][1]
            >= selection.selected_keep_ranges[i + 1][0]
        ):
            raise ValueError("Overlapping or unsorted ranges in selection file")
