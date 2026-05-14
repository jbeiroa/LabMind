import pandas as pd
from typing import List, Dict, Any, Tuple


def flags_to_ranges(ts: pd.Series, flags: pd.Series, label: str) -> List[Dict[str, Any]]:
    """Converts a boolean series of flags into a list of [start, end] ranges."""
    ranges = []
    if flags.sum() == 0:
        return ranges

    # Find contiguous groups of True flags
    is_anomaly = flags.astype(int)
    # 1 where it becomes anomaly, -1 where it stops being anomaly
    diff = is_anomaly.diff().fillna(is_anomaly.iloc[0])
    
    starts = ts[diff == 1].tolist()
    # For ends, we want the LAST point where it WAS an anomaly
    # diff == -1 means CURRENT point is 0, PREVIOUS was 1.
    # So we shift ts to get the previous point's timestamp.
    ends = ts.shift(1)[diff == -1].tolist()
    
    # Handle the case where it ends with an anomaly
    if is_anomaly.iloc[-1] == 1:
        ends.append(ts.iloc[-1])

    for s, e in zip(starts, ends):
        ranges.append({
            "label": label,
            "start_ts_ms": int(s),
            "end_ts_ms": int(e),
            "confidence": 1.0
        })
    return ranges


def merge_adjacent_ranges(
    ranges: List[Dict[str, Any]], merge_gap_ms: int, min_segment_len_ms: int
) -> List[Dict[str, Any]]:
    """Merges ranges that are closer than merge_gap_ms and filters out tiny segments."""
    if not ranges:
        return []

    # Sort by start time
    sorted_ranges = sorted(ranges, key=lambda x: x["start_ts_ms"])
    
    merged = []
    if not sorted_ranges:
        return merged

    current = sorted_ranges[0].copy()

    for next_range in sorted_ranges[1:]:
        if next_range["start_ts_ms"] - current["end_ts_ms"] <= merge_gap_ms:
            current["end_ts_ms"] = max(current["end_ts_ms"], next_range["end_ts_ms"])
            # Combine reason codes if they exist? For now just keep label
        else:
            if current["end_ts_ms"] - current["start_ts_ms"] >= min_segment_len_ms:
                merged.append(current)
            current = next_range.copy()
    
    if current["end_ts_ms"] - current["start_ts_ms"] >= min_segment_len_ms:
        merged.append(current)
        
    return merged


def complement_keep_ranges(
    data_start_ts_ms: int, data_end_ts_ms: int, anomaly_ranges: List[Dict[str, Any]]
) -> List[Tuple[int, int]]:
    """Inverts anomaly ranges to find 'keep' ranges within the data bounds."""
    if not anomaly_ranges:
        return [(data_start_ts_ms, data_end_ts_ms)]

    # Sort anomaly ranges
    sorted_anomalies = sorted(anomaly_ranges, key=lambda x: x["start_ts_ms"])
    
    keep_ranges = []
    current_ts = data_start_ts_ms

    for anomaly in sorted_anomalies:
        if anomaly["start_ts_ms"] > current_ts:
            keep_ranges.append((current_ts, anomaly["start_ts_ms"] - 1))
        current_ts = max(current_ts, anomaly["end_ts_ms"] + 1)

    if current_ts <= data_end_ts_ms:
        keep_ranges.append((current_ts, data_end_ts_ms))

    return keep_ranges


def normalize_keep_ranges(keep_ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Ensures keep ranges are sorted and non-overlapping."""
    if not keep_ranges:
        return []
    
    sorted_ranges = sorted(keep_ranges, key=lambda x: x[0])
    normalized = []
    
    if not sorted_ranges:
        return normalized

    curr_start, curr_end = sorted_ranges[0]
    for next_start, next_end in sorted_ranges[1:]:
        if next_start <= curr_end + 1:
            curr_end = max(curr_end, next_end)
        else:
            normalized.append((curr_start, curr_end))
            curr_start, curr_end = next_start, next_end
    
    normalized.append((curr_start, curr_end))
    return normalized


def apply_keep_ranges(df: pd.DataFrame, keep_ranges: List[Tuple[int, int]]) -> pd.DataFrame:
    """Filters a DataFrame to only include rows within the specified keep ranges."""
    if not keep_ranges:
        return df.iloc[0:0]  # Empty but with same columns

    mask = pd.Series(False, index=df.index)
    for start, end in keep_ranges:
        mask |= (df["timestamp_ms"] >= start) & (df["timestamp_ms"] <= end)
    
    return df[mask].copy()
