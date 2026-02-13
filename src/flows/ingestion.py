import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from metaflow import FlowSpec, Parameter, current, step

from flows.contracts import (
    CANONICAL_COLUMNS,
    REQUIRED_RAW_FIELDS,
    InputFormat,
    IngestionMetadata,
    SourceMode,
    build_parquet_path,
    utc_now_iso
)


class IngestionFlow(FlowSpec):

    source_mode = Parameter("source_mode", type=str,
                            help="Flow mode: 'live' or 'file'", 
                            default="live")
    experiment_id = Parameter("experiment_id",
                              help="Unique identifier for an experiment, defaults to date", 
                              default=datetime.now().strftime("%Y%m%d"))
    trial_id = Parameter("trial_id", type=str,
                         help="Unique identifier for a trial run, defaults to time of day", 
                         default=datetime.now().strftime("%H%M%s"))
    sensor_id = Parameter("sensor-id", type=str,
                          help="Sensor ID of experiment run",
                          default="HC-SR04")
    unit = Parameter("unit", type=str,
                     help="Measurement units of experiment run",
                     default="cm")
    save_parquet = Parameter("save-parquet", type=bool,
                             help="Option to save data to parquet",
                             default=True)
    output_dir = Parameter("output-dir", type=str,
                           help="Path to output directory", 
                           default="data/raw")
    raw_output_file = Parameter(
        "raw-output-file",
        type=str,
        help="Custom jsonl path for raw live capture. If empty, uses run-scoped default.",
        default="",
    )
    persist_raw_jsonl = Parameter(
        "persist-raw-jsonl",
        type=bool,
        help="Keep raw jsonl snapshot after dataframe/parquet generation.",
        default=True,
    )
    strict_schema = Parameter("strict-schema", type=bool,
                              help="Use strict schema for dataframe",
                              default=True)
    
    # live-mode params
    duration_s = Parameter("duration-s",
                           help="Measurement loop duration in seconds",
                           type=float, default=5.0)
    serial_baud = Parameter("serial-baud", 
                            help="Baudrate of serial port connection",
                            type=int, default=115200)
    serial_port = Parameter("serial-port", 
                            help="Serial port name",
                            type=str, default="")
    batch_size = Parameter("batch-size", 
                           help="Measurement batch size",
                           type=int, default=25)
    batch_flush_s = Parameter("batch-flush-s", 
                              help="Flush interval for batch readings",
                              type=float, default=0.2)
    ingest_url = Parameter("ingest-url", 
                           help="Ingestion API url",
                           default="http://localhost:8002/reading")
    raw_jsonl_path = Parameter("raw-jsonl-path", type=str,
                               help="Path to jsonl file",
                               default="data/raw/readings.jsonl")

    # file mode params
    input_file = Parameter("input-file", type=str,
                           help="Path of input file for 'file' mode",
                           default="")
    input_format = Parameter("input-format", type=str,
                             help="Format of input file",
                             default="")

    @step
    def start(self):
        self.started_at_utc = utc_now_iso()
        self._validate_mode()

        self.ingestion_metadata: IngestionMetadata = {
            "source_mode": self._source_mode(),
            "source_snapshot_path": "",
            "experiment_id": self.experiment_id,
            "trial_id": self.trial_id,
            "sensor_id": self.sensor_id,
            "unit": self.unit,
            "strict_schema": self.strict_schema,
            "row_count": 0,
            "dropped_row_count": 0,
            "duration_s": self.duration_s if self._source_mode() == "live" else None,
            "serial_port": self.serial_port or None,
            "serial_baud": self.serial_baud if self._source_mode() == "live" else None,
            "ingest_url": self.ingest_url if self._source_mode() == "live" else None,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": "",
        }
        self.next(self.acquire_or_load)

    @step
    def acquire_or_load(self):
        self._cleanup_raw_snapshot = False
        if self.source_mode == "live":
            resolved_raw_path, cleanup_after_run = self._resolve_live_raw_path()
            self.live_raw_path = str(resolved_raw_path)
            self._cleanup_raw_snapshot = cleanup_after_run
            self._run_live_ingestion()
            snapshot = Path(self.live_raw_path)
            self.source_snapshot_path = str(snapshot)
            raw_records = self._load_jsonl(snapshot)

        else:
            snapshot = Path(self.input_file)
            self.source_snapshot_path = str(snapshot)
            raw_records = self._load_from_file(snapshot, self._resolved_input_format(snapshot))

        self.ingestion_metadata["source_snapshot_path"] = self.source_snapshot_path
        if not raw_records:
            diagnostics = (
                f"No raw rows loaded from snapshot: {self.source_snapshot_path}. "
                f"source_mode={self._source_mode()}."
            )
            if self._source_mode() == "live":
                stdout_tail = (self.live_stdout or "").strip().splitlines()[-5:]
                stderr_tail = (self.live_stderr or "").strip().splitlines()[-5:]
                diagnostics += (
                    f" live_returncode={self.live_returncode}. "
                    f"live_stdout_tail={stdout_tail}. "
                    f"live_stderr_tail={stderr_tail}."
                )
            raise ValueError(diagnostics)

        self.raw_records = raw_records
        self.next(self.validate_and_normalize)

    @step
    def validate_and_normalize(self):
        valid_rows: list[dict[str, Any]] = []
        dropped = 0
        ingested_at = utc_now_iso()

        for row in self.raw_records:
            if not all(field in row for field in REQUIRED_RAW_FIELDS):
                dropped += 1
                continue
            try:
                timestamp_ms = int(row["timestamp_ms"])
                value = float(row["value"])
            except (TypeError, ValueError):
                dropped += 1
                continue

            valid_rows.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "value": value,
                    "experiment_id": self.experiment_id,
                    "trial_id": self.trial_id,
                    "sensor_id": self.sensor_id,
                    "unit": self.unit,
                    "source": self._source_mode(),
                    "ingested_at": ingested_at,
                }
            )

        if dropped > 0 and self.strict_schema:
            raise ValueError(f"Malformed rows found: {dropped} (strict-schema=true)")

        if not valid_rows:
            raise ValueError(
                "No valid rows after validation. "
                f"source_snapshot_path={self.source_snapshot_path}; "
                f"raw_rows={len(self.raw_records)}; dropped_rows={dropped}; "
                f"strict_schema={self.strict_schema}"
            )

        df = pd.DataFrame(valid_rows)
        df = df[list(CANONICAL_COLUMNS)].sort_values("timestamp_ms").reset_index(drop=True)

        self.readings_df = df
        self.row_count = int(len(df))
        self.dropped_row_count = int(dropped)
        self.data_start_ts_ms = int(df["timestamp_ms"].min())
        self.data_end_ts_ms = int(df["timestamp_ms"].max())

        self.ingestion_metadata["row_count"] = self.row_count
        self.ingestion_metadata["dropped_row_count"] = self.dropped_row_count
        self.next(self.persist_optional_parquet)

    @step
    def persist_optional_parquet(self):
        if self.save_parquet:
            parquet_path = build_parquet_path(
                output_dir=self.output_dir,
                experiment_id=self.experiment_id,
                trial_id=self.trial_id,
                sensor_id=self.sensor_id,
                run_id=current.run_id,
                dt=datetime.now(UTC),
            )
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            self.readings_df.to_parquet(parquet_path, index=False)
            self.output_parquet_path = str(parquet_path)
        else:
            self.output_parquet_path = None

        self.finished_at_utc = utc_now_iso()
        self.ingestion_metadata["finished_at_utc"] = self.finished_at_utc

        if self._cleanup_raw_snapshot and self.source_snapshot_path:
            snapshot_path = Path(self.source_snapshot_path)
            if snapshot_path.exists():
                snapshot_path.unlink()
            self.source_snapshot_path = ""
            self.ingestion_metadata["source_snapshot_path"] = ""

        self.next(self.end)

    @step
    def end(self):
        parquet_path = (
            str(Path(self.output_parquet_path).resolve())
            if self.output_parquet_path
            else None
        )
        print(
            f"source={self._source_mode()} rows={self.row_count} dropped={self.dropped_row_count} "
            f"parquet={parquet_path}"
        )

    # ---------------- helpers ----------------

    def _source_mode(self) -> SourceMode:
        mode = self.source_mode.strip().lower()
        if mode not in {"live", "file"}:
            raise ValueError("source-mode must be one of: live, file")
        return mode  # type: ignore[return-value]

    def _validate_mode(self) -> None:
        if self._source_mode() == "file" and not self.input_file.strip():
            raise ValueError("input-file is required when source-mode=file")
        
    def _run_live_ingestion(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": "src",
                "LABMIND_LOOP_DURATION_S": str(self.duration_s),
                "LABMIND_SERIAL_BAUD": str(self.serial_baud),
                "LABMIND_BATCH_SIZE": str(self.batch_size),
                "LABMIND_BATCH_FLUSH_S": str(self.batch_flush_s),
                "LABMIND_INGEST_URL": self.ingest_url,
                "LABMIND_RAW_DATA_FILE": self.live_raw_path,
            }
        )
        if self.serial_port.strip():
            env["LABMIND_SERIAL_PORT"] = self.serial_port.strip()

        cmd = ["uv", "run", "python", "src/ingestion/serial_reader.py"]
        proc = subprocess.run(cmd, env=env, text=True, capture_output=True)

        # keep logs available in artifacts for debugging
        self.live_stdout = proc.stdout
        self.live_stderr = proc.stderr
        self.live_returncode = proc.returncode

        if proc.returncode != 0:
            raise RuntimeError(
                f"Live ingestion subprocess failed with code {proc.returncode}.\n"
                f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
            )

    def _resolve_live_raw_path(self) -> tuple[Path, bool]:
        if self.raw_output_file.strip():
            return Path(self.raw_output_file.strip()), False

        if self.persist_raw_jsonl:
            date_str = datetime.now(UTC).date().isoformat()
            default_path = (
                Path(self.output_dir)
                / f"experiment_id={self.experiment_id}"
                / f"trial_id={self.trial_id}"
                / f"sensor_id={self.sensor_id}"
                / f"date={date_str}"
                / f"raw-{current.run_id}.jsonl"
            )
            return default_path, False

        temp_path = (
            Path(self.output_dir)
            / ".tmp"
            / f"raw-{self.experiment_id}-{self.trial_id}-{current.run_id}.jsonl"
        )
        return temp_path, True
    
    def _resolved_input_format(self, input_path: Path) -> InputFormat:
        if self.input_format:
            fmt = self.input_format.strip().lower()
        else:
            suffix = input_path.suffix.lower().lstrip(".")
            fmt = suffix

        if fmt not in {"jsonl", "csv", "parquet"}:
            raise ValueError("input-format must be jsonl, csv, or parquet")
        return fmt  # type: ignore[return-value]
        
    def _load_from_file(self, input_path: Path, fmt: InputFormat) -> list[dict[str, Any]]:
        if not input_path.exists():
            raise FileNotFoundError(f"Input file does not exist: {input_path}")

        if fmt == "jsonl":
            return self._load_jsonl(input_path)

        if fmt == "csv":
            df = pd.read_csv(input_path)
            return df.to_dict(orient="records")

        # parquet
        df = pd.read_parquet(input_path)
        return df.to_dict(orient="records")

    def _load_jsonl(self, input_path: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if not input_path.exists():
            raise FileNotFoundError(f"JSONL file does not exist: {input_path}")
        with input_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))

        return records


if __name__ == "__main__":
    IngestionFlow()
