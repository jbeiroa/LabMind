import numpy as np
import pandas as pd
from typing import Tuple, Optional


def compute_physical_bound_flags(
    df: pd.DataFrame, min_value: Optional[float], max_value: Optional[float]
) -> pd.Series:
    """Flags values outside specified physical bounds."""
    mask = pd.Series(False, index=df.index)
    if min_value is not None:
        mask |= df["value"] < min_value
    if max_value is not None:
        mask |= df["value"] > max_value
    return mask


def compute_jump_flags(df: pd.DataFrame, max_abs_jump: float) -> pd.Series:
    """Flags sudden jumps between adjacent measurements."""
    if len(df) < 2:
        return pd.Series(False, index=df.index)
    
    jumps = df["value"].diff().abs()
    return jumps > max_abs_jump


def compute_mad_flags(
    df: pd.DataFrame, rolling_window: int, mad_z_threshold: float
) -> Tuple[pd.Series, pd.Series]:
    """
    Computes Median Absolute Deviation (MAD) flags and anomaly scores.
    Returns (is_outlier_flag, anomaly_score).
    """
    if len(df) < rolling_window:
        # Fallback to global MAD if window is too small, or just return zeros
        rolling_median = df["value"].median()
    else:
        rolling_median = df["value"].rolling(window=rolling_window, center=True).median()
        # Fill NaNs from rolling window at edges
        rolling_median = rolling_median.ffill().bfill()

    abs_deviation = (df["value"] - rolling_median).abs()
    
    if len(df) < rolling_window:
        mad = abs_deviation.median()
    else:
        mad = abs_deviation.rolling(window=rolling_window, center=True).median()
        mad = mad.ffill().bfill()

    # Avoid division by zero
    mad = mad.replace(0, 1e-9)
    
    # 0.6745 is the scaling factor for MAD to be comparable to standard deviation for normal dist
    z_scores = 0.6745 * abs_deviation / mad
    
    flags = z_scores > mad_z_threshold
    return flags, z_scores


def combine_flags(*flags: pd.Series) -> pd.Series:
    """Combines multiple boolean series using OR."""
    combined = pd.Series(False, index=flags[0].index)
    for f in flags:
        combined |= f
    return combined


def annotate_reasons(
    df: pd.DataFrame,
    bound_flags: pd.Series,
    jump_flags: pd.Series,
    mad_flags: pd.Series
) -> pd.Series:
    """Returns a series of pipe-delimited reason codes."""
    reasons = pd.Series("", index=df.index)
    
    reasons.loc[bound_flags] += "PHYSICAL_BOUND|"
    reasons.loc[jump_flags] += "JUMP|"
    reasons.loc[mad_flags] += "OUTLIER_MAD|"
    
    # Strip trailing pipe
    return reasons.str.rstrip("|")
