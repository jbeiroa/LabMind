set shell := ["zsh", "-cu"]

ingestion-api:
  PYTHONPATH=src \
  RAW_DATA_DIR="${RAW_DATA_DIR:-data/raw}" \
  RAW_DATA_FILE="${RAW_DATA_FILE:-data/raw/readings.jsonl}" \
  uv run python -m uvicorn api.ingestion_api:app --host ${INGESTION_API_HOST:-0.0.0.0} --port ${INGESTION_API_PORT:-8002}

ingest-serial:
  PYTHONPATH=src uv run python -m flows.ingestion run --source_mode live --persist-raw-jsonl ${PERSIST_RAW_JSONL:-true} --save-parquet ${SAVE_PARQUET:-true}

ingest-serial-flags *FLOW_ARGS:
  PYTHONPATH=src uv run python -m flows.ingestion run --source_mode live {{FLOW_ARGS}}

serial-capture:
  PYTHONPATH=src \
  LABMIND_INGEST_URL="${LABMIND_INGEST_URL:-http://localhost:8002/reading}" \
  LABMIND_RAW_DATA_FILE="${LABMIND_RAW_DATA_FILE:-}" \
  LABMIND_INGEST_TIMEOUT_S="${LABMIND_INGEST_TIMEOUT_S:-2}" \
  LABMIND_BATCH_SIZE="${LABMIND_BATCH_SIZE:-25}" \
  LABMIND_BATCH_FLUSH_S="${LABMIND_BATCH_FLUSH_S:-0.2}" \
  LABMIND_SERIAL_BAUD="${LABMIND_SERIAL_BAUD:-115200}" \
  LABMIND_LOOP_DURATION_S="${LABMIND_LOOP_DURATION_S:-5}" \
  uv run python src/ingestion/serial_reader.py
