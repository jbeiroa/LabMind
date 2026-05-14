# LabMind Project Context

LabMind is a sensor-to-ML workflow project designed for running physical experiments (currently focusing on Arduino + ultrasonic sensors), capturing raw measurements, and producing reproducible analysis artifacts.

## Project Overview

The system bridges physical hardware (Arduino) with machine learning workflows using a service-oriented architecture combined with Metaflow orchestration.

### Core Architecture

1.  **Hardware Interaction:** An Arduino sketch (`src/arduino/`) emits measurements over Serial.
2.  **Serial Ingestion:** A `serial_reader.py` client reads measurements from the Serial port and batches them to an Ingestion API.
3.  **Ingestion API:** A FastAPI service (`src/api/ingestion_api.py`) receives readings and persists them to an append-only JSONL "raw store".
4.  **Workflow Orchestration:** `IngestionFlow` (`src/flows/ingestion.py`) using Metaflow handles the end-to-end data lifecycle:
    *   **Live Mode:** Spawns the serial reader, captures data, and then processes it.
    *   **File Mode:** Loads data from existing JSONL, CSV, or Parquet files.
    *   **Validation:** Enforces a canonical schema and drops or fails on malformed data.
    *   **Persistence:** Saves validated data into structured Parquet snapshots.

### Tech Stack

*   **Language:** Python >= 3.12
*   **Orchestration:** Metaflow
*   **API Framework:** FastAPI
*   **Data Processing:** Pandas, Parquet, JSONL
*   **Dependency Management:** `uv`
*   **Command Runner:** `just`
*   **Testing:** `pytest`

## Key Data Contracts

### Raw Reading (JSONL)
```json
{"device_id":"HC-SR04","timestamp_ms":1234,"value":42.0}
```

### Canonical Schema (DataFrame/Parquet)
*   `timestamp_ms`: Event time in milliseconds.
*   `value`: Measured sensor value.
*   `experiment_id`: Unique identifier for the experiment.
*   `trial_id`: Unique identifier for the specific trial.
*   `sensor_id`: Identifier for the sensor used.
*   `unit`: Measurement unit (e.g., "cm").
*   `source`: Data source ("live" or "file").
*   `ingested_at`: ISO timestamp of ingestion.

## Building and Running

The project uses `just` to simplify common tasks.

| Task | Command | Description |
| :--- | :--- | :--- |
| **Install** | `uv sync` | Install dependencies using `uv`. |
| **API** | `just ingestion-api` | Start the ingestion API service (Port 8002). |
| **Live Ingest** | `just ingest-serial` | Run Metaflow `IngestionFlow` in live mode (requires API). |
| **Serial Only** | `just serial-capture` | Run `serial_reader.py` directly (bypasses Metaflow). |
| **Test** | `pytest` | Run the test suite. |

### Environment Variables

*   `RAW_DATA_DIR`: Directory for raw JSONL files (default: `data/raw`).
*   `RAW_DATA_FILE`: Default target JSONL file (default: `data/raw/readings.jsonl`).
*   `LABMIND_INGEST_URL`: Target API URL for serial reader.
*   `LABMIND_SERIAL_BAUD`: Baud rate for Arduino serial (default: `115200`).

## Development Conventions

*   **Separation of Concerns:** Keep hardware-specific logic in `src/ingestion/`, API logic in `src/api/`, and workflow logic in `src/flows/`.
*   **Immutability:** Raw JSONL files are intended to be append-only, immutable records of events.
*   **Environment Aware:** Serial ingestion (USB) usually requires running on the host (macOS/Linux), while the API and Metaflow can run in the DevContainer.
*   **Strict Validation:** By default, `IngestionFlow` uses `strict-schema=true`, which fails the flow if malformed rows are encountered.
*   **Storage Hierarchy:** Data is organized under `data/raw/` by `experiment_id`, `trial_id`, and `sensor_id` to ensure clarity and reproducibility.

## Key Files

*   `src/flows/ingestion.py`: The main Metaflow entry point.
*   `src/api/ingestion_api.py`: FastAPI server for raw data persistence.
*   `src/ingestion/serial_reader.py`: The bridge between Serial hardware and the API.
*   `src/flows/contracts.py`: Definition of shared data structures and schema constants.
*   `Justfile`: Centralized command definitions.
