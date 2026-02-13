# LabMind

LabMind is a sensor-to-ML workflow project for running physical experiments (currently Arduino + ultrasonic sensor), capturing raw measurements, and producing reproducible analysis artifacts.

## 1. Overview

LabMind combines:

- Online ingestion services (serial + API)
- Offline orchestration with Metaflow
- Raw immutable event capture (JSONL)
- Analysis-ready snapshots (Parquet + DataFrame artifacts)

The current implementation focus is the ingestion path and ingestion flow orchestration.

## 2. Quickstart

### Prerequisites

- Python `>=3.12`
- [`uv`](https://docs.astral.sh/uv/)
- [`just`](https://github.com/casey/just) (required on host for serial workflows)
- Arduino connected over USB (for live ingestion)

### Clone and install

```bash
git clone <your-repo-url>
cd LabMind
uv sync
```

### Host vs devcontainer: where commands should run

- **Devcontainer (recommended):** run API service and file-based flow runs.
- **Host macOS/Linux:** run serial capture/live ingestion commands (USB serial access).

### Fast start

1. Start ingestion API (usually in devcontainer):

```bash
just ingestion-api
```

2. Run live ingestion flow (usually on host):

```bash
just ingest-serial
```

## 3. Project Structure

```text
labmind/
├── .devcontainer/
├── data/                      # runtime data (gitignored)
│   └── raw/
├── notebooks/
├── src/
│   ├── api/
│   │   ├── bridge.py
│   │   └── ingestion_api.py
│   ├── arduino/
│   │   └── read_ultrasonic_sensor/
│   │       └── read_ultrasonic_sensor.ino
│   ├── flows/
│   │   ├── contracts.py
│   │   └── ingestion.py
│   └── ingestion/
│       └── serial_reader.py
├── tests/
│   ├── test_bridge_api.py
│   └── test_ingestion_api.py
├── Justfile
├── pyproject.toml
├── uv.lock
└── README.md
```

## 4. Data Contracts and Storage

### Raw ingestion row (JSONL)

```json
{"device_id":"HC-SR04","timestamp_ms":1234,"value":42.0}
```

Fields:

- `device_id: str`
- `timestamp_ms: int`
- `value: float`

### Canonical ingestion flow schema (DataFrame/Parquet)

- `timestamp_ms`
- `value`
- `experiment_id`
- `trial_id`
- `sensor_id`
- `unit`
- `source`
- `ingested_at`

### Storage paths

- Default raw JSONL (API default):
  - `data/raw/readings.jsonl`
- Run-scoped raw JSONL (live flow + `persist_raw_jsonl=true`):
  - `data/raw/experiment_id=<id>/trial_id=<id>/sensor_id=<id>/date=<yyyy-mm-dd>/raw-<run_id>.jsonl`
- Parquet snapshot (when `save_parquet=true`):
  - `data/raw/experiment_id=<id>/trial_id=<id>/sensor_id=<id>/date=<yyyy-mm-dd>/part-<run_id>.parquet`
- Temporary raw file (when `persist_raw_jsonl=false`, removed post-validation):
  - `data/raw/.tmp/raw-<experiment_id>-<trial_id>-<run_id>.jsonl`

## 5. Ingestion Services

### Ingestion API (`src/api/ingestion_api.py`)

Responsibilities:

- Accept single reading: `POST /reading`
- Accept batch readings: `POST /readings`
- Persist rows to JSONL (append-only)

Request contract:

- Body for `POST /reading`: one reading object
- Body for `POST /readings`: array of reading objects
- Optional header: `X-Raw-Data-File` (override target JSONL path per request)

Environment variables:

- `RAW_DATA_DIR` (default `data/raw`)
- `RAW_DATA_FILE` (default `data/raw/readings.jsonl`)

### Serial Reader (`src/ingestion/serial_reader.py`)

Responsibilities:

- Connect to Arduino serial device
- Parse `timestamp_ms,value` lines
- Batch and send readings to ingestion API

Key environment variables:

- `LABMIND_INGEST_URL` (default `http://localhost:8002/reading`)
- `LABMIND_INGEST_BATCH_URL` (default inferred to `/readings`)
- `LABMIND_INGEST_TIMEOUT_S` (default `2`)
- `LABMIND_BATCH_SIZE` (default `25`)
- `LABMIND_BATCH_FLUSH_S` (default `0.2`)
- `LABMIND_SERIAL_BAUD` (default `115200`)
- `LABMIND_LOOP_DURATION_S` (default `5`)
- `LABMIND_RAW_DATA_FILE` (optional custom JSONL target path via API header)

## 6. Metaflow Ingestion Flow

Flow module: `src/flows/ingestion.py`

The `IngestionFlow` supports two modes:

- `source_mode=live`: runs serial ingestion subprocess, then validates and transforms
- `source_mode=file`: loads `jsonl|csv|parquet`, then validates and transforms

### Core parameters

- `source_mode`
- `experiment_id`
- `trial_id`
- `sensor-id`
- `unit`
- `save-parquet`
- `persist-raw-jsonl`
- `raw-output-file`
- `output-dir`
- `strict-schema`

### Live-mode parameters

- `duration-s`
- `serial-baud`
- `serial-port`
- `batch-size`
- `batch-flush-s`
- `ingest-url`

### File-mode parameters

- `input-file`
- `input-format`

### Output artifacts

- `readings_df`
- `row_count`
- `dropped_row_count`
- `data_start_ts_ms`
- `data_end_ts_ms`
- `output_parquet_path`
- `ingestion_metadata`
- `source_snapshot_path`

### Validation behavior

- If malformed rows exist and `strict-schema=true`: flow fails.
- If malformed rows exist and `strict-schema=false`: malformed rows are dropped.
- If no raw rows are loaded in live mode: failure includes diagnostics with serial subprocess output tail.

## 7. End-to-End Workflows (Live and File)

### Command matrix

Start ingestion API:

```bash
just ingestion-api
```

Start ingestion API with custom storage/location:

```bash
RAW_DATA_DIR=data/raw/custom RAW_DATA_FILE=data/raw/custom/run.jsonl INGESTION_API_PORT=8002 just ingestion-api
```

Run serial capture only (no Metaflow flow):

```bash
just serial-capture
```

Run live ingestion flow (default toggles):

```bash
just ingest-serial
```

Run live ingestion flow without raw JSONL persistence:

```bash
PERSIST_RAW_JSONL=false just ingest-serial
```

Run live ingestion flow without parquet persistence:

```bash
SAVE_PARQUET=false just ingest-serial
```

Run live ingestion flow without raw JSONL and without parquet:

```bash
PERSIST_RAW_JSONL=false SAVE_PARQUET=false just ingest-serial
```

Run live ingestion flow with advanced flags:

```bash
just ingest-serial-flags "--duration-s" "10" "--serial-baud" "115200" "--raw-output-file" "data/raw/custom-live.jsonl"
```

Run file-mode ingestion flow:

```bash
PYTHONPATH=src uv run python -m flows.ingestion run \
  --source_mode file \
  --input-file data/raw/readings.jsonl \
  --input-format jsonl \
  --experiment_id exp_001 \
  --trial_id t01
```

### Where are my parquet files?

Parquet is written only when `save-parquet=true`.

At flow end, the run prints the resolved parquet path. By default, it is under:

- `data/raw/experiment_id=<id>/trial_id=<id>/sensor_id=<id>/date=<yyyy-mm-dd>/part-<run_id>.parquet`

If `save-parquet=false`, no parquet file is written and `output_parquet_path=None`.

## 8. Troubleshooting

### No rows acquired (`No raw rows loaded from snapshot...`)

Check:

- Arduino is connected and readable on host
- correct baud rate (current sketch uses `115200`)
- ingestion API is running and reachable at configured URL

### API returns HTTP 500 in live mode

Common cause: raw file path sent by host is not writable in API runtime context (e.g., host temp path while API runs in container).

Use project-local shared paths such as under `data/raw/...`.

### `No valid rows after validation`

This means loaded rows were empty or invalid after schema checks.

- Verify source file contents (`timestamp_ms`, `value` present and numeric)
- If needed, run with `--strict-schema false` to drop malformed rows

### Serial commands run inside devcontainer fail

On macOS devcontainer setups, USB serial is typically host-only.

- Run `just serial-capture` / `just ingest-serial` on host
- Keep API running in devcontainer and exposed on `8002`

## 9. Extended Architecture and Specification

This section preserves the broader project direction. Items marked **Planned** are not fully implemented yet.

### Core objectives

- Ingest and store raw sensor data from physical experiments
- Detect and handle noise/anomalies
- Fit physically meaningful models
- Enforce physics constraints and interpretability
- Generate structured reports

### High-level architecture (current + planned)

```text
Arduino Sensor
     ↓
Serial Ingestion Service (implemented)
     ↓
Ingestion API (implemented)
     ↓
Raw JSONL Store (implemented)
     ↓
Metaflow IngestionFlow (implemented)
     ↓
Validated Parquet Snapshot (implemented, optional)
     ↓
ExperimentAnalysisFlow / ModelSelectionFlow / AnomalyBacktestFlow (planned)
     ↓
Model & Report Artifacts (planned)
     ↓
FastAPI Serving Layer (partially planned)
```

### Technology stack

- Language: Python `>=3.12`
- Workflow orchestration: Metaflow
- Serving layer: FastAPI
- Data: Pandas + Parquet + JSONL
- Dependencies: uv
- Testing: pytest
- Dev environment: devcontainer + host serial workflow

### Human-in-the-loop principles

Humans remain explicit decision points for:

- experiment setup
- segmentation/validation review
- model selection overrides
- interpretation review

### Planned pipelines (not yet fully implemented)

- `ExperimentAnalysisFlow`
- `ModelSelectionFlow`
- `AnomalyBacktestFlow`

These are design targets and should be treated as roadmap items until code lands in `src/flows/`.
