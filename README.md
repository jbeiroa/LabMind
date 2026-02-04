# LabMind — Full Project Specification

## 1. Overview

**LabMind** is a production-grade ML engineering system that autonomously analyzes experimental sensor data from low-cost scientific setups (e.g., Arduino-based laboratories). The system is designed to support real-world, noisy experiments by combining reproducible ML pipelines, agent-based reasoning, physics constraints, and explicit human-in-the-loop checkpoints.

The project is intentionally aligned with the **ml.school** curriculum and tooling, emphasizing reproducibility, evaluation, trust, and correct separation between offline ML workflows and online services.

---

## 2. Core Objectives

* Ingest and store raw sensor data from physical experiments
* Detect and handle noise, anomalies, and experimental artifacts
* Automatically select and fit physically meaningful models
* Enforce physics-based constraints and interpretability
* Generate structured scientific reports
* Keep humans explicitly in control of key decisions

---

## 3. Technology Stack

### Core Technologies

* **Language:** Python 3.11
* **Workflow Orchestration:** Metaflow
* **Agent Framework:** Google ADK
* **Experiment Tracking:** MLflow
* **Dependency Management:** uv
* **Containerization:** Docker
* **Development Environment:** Devcontainers
* **Serving Layer:** FastAPI
* **Data Storage:** Parquet + Pandas
* **Modeling:** NumPy, SciPy, scikit-learn
* **Testing:** Pytest

---

## 4. High-Level Architecture

```
Arduino Sensor
     ↓
Serial Ingestion Service
     ↓
Raw Data Store (Parquet)
     ↓
Metaflow Pipelines
  ├─ Data Validation & Segmentation
  ├─ Anomaly Detection
  ├─ Model Selection & Fitting
  ├─ Physics Validation
  └─ Evaluation & Backtesting
     ↓
Model & Report Artifacts
     ↓
FastAPI Service
     ↓
Human Users (Dashboard / Reports)
```

---

## 5. Data Model

### Canonical Schema

```
timestamp | experiment_id | trial_id | sensor_id | value | unit
```

### Storage Layout

```
data/
├── raw/
├── validated/
├── features/
├── artifacts/
├── reports/
```

---

## 6. Metaflow Pipelines

### 6.1 ExperimentAnalysisFlow

**Purpose:** End-to-end analysis of a single experimental trial.

**Steps:**

1. Load raw data snapshot
2. Validate schema and units
3. Segment time series into regimes
4. Detect and mask anomalies
5. Fit candidate models (parallel)
6. Validate physical plausibility
7. Select final model
8. Generate interpretation and report

All steps are reproducible, versioned, and replayable.

---

### 6.2 ModelSelectionFlow

**Purpose:** Compare multiple candidate models under identical conditions.

**Candidate Models:**

* Linear
* Quadratic
* Exponential
* Sinusoidal

**Metrics:**

* RMSE
* AIC / BIC
* Residual structure
* Physics constraint violations

Results are logged to MLflow and stored as Metaflow artifacts.

---

### 6.3 AnomalyBacktestFlow

**Purpose:** Validate anomaly detection logic using synthetic and historical data.

**Metrics:**

* Precision / Recall
* Detection latency
* False positive rate

Used in CI to prevent regressions.

---

## 7. Agent System (Google ADK)

Agents do not replace ML pipelines; they interpret, validate, explain, and assist decision-making.

### Agent Roles

1. **Data Monitor Agent**

   * Validates incoming data
   * Segments time series
   * Detects anomalies

2. **Model Analyst Agent**

   * Interprets model fitting results
   * Explains model selection decisions

3. **Physics Validator Agent**

   * Applies domain constraints (units, monotonicity, curvature)
   * Rejects physically implausible models

4. **Experiment Advisor Agent**

   * Suggests improvements or repetitions
   * Highlights data quality issues

5. **Report Writer Agent**

   * Produces structured scientific reports

---

## 8. System Behavior Specification (Canonical Use Case)

### Scenario: Free-Fall Experiment with Ultrasonic Distance Sensor

An ultrasonic sensor measures the distance to an object that is initially held still, released into free fall, and eventually comes to rest.

The raw signal contains:

* Initial stationary readings
* Noise and misreadings from hand placement
* A quadratic distance-vs-time segment during free fall
* Final stationary readings

---

### Step-by-Step System Behavior

#### Step 0 — Experiment Setup (Human-Controlled)

* Human selects sensor and experiment type
* Starts data acquisition
* System assigns `experiment_id` and `trial_id`

*No ML decisions occur at this stage.*

---

#### Step 1 — Data Ingestion

* Serial ingestion service records timestamped readings
* Data is written verbatim to `data/raw/`

*Data is immutable once recorded.*

---

#### Step 2 — Analysis Trigger

* Human explicitly triggers analysis (or ingestion completes)
* `ExperimentAnalysisFlow` starts

---

#### Step 3 — Segmentation & Validation

**Agent:** Data Monitor Agent

* Validates schema and units
* Segments the signal into:

  * Stationary (pre-release)
  * Noisy transition (hand interference)
  * Motion (free fall)
  * Stationary (post-impact)

**Human-in-the-loop checkpoint:**

* UI displays segmentation
* Human may adjust boundaries
* Any adjustment triggers a new Metaflow run

---

#### Step 4 — Anomaly Detection

**Agent:** Data Monitor Agent

* Flags outliers and implausible jumps
* Anomalies are masked, not deleted

**Optional human review** of anomaly mask

---

#### Step 5 — Model Fitting

**Agent:** Model Analyst Agent

* Fits candidate models using only the motion segment
* Runs in parallel via Metaflow `foreach`
* Logs metrics and parameters to MLflow

---

#### Step 6 — Physics Validation

**Agent:** Physics Validator Agent

* Evaluates curvature sign
* Checks monotonicity
* Ensures non-negative distances

Physically invalid models are rejected.

---

#### Step 7 — Model Selection

**Agent:** Model Analyst Agent

* Selects the simplest valid model with best performance
* Produces explanation for acceptance and rejection

**Human-in-the-loop checkpoint:**

* Human may override model choice
* Override is logged and versioned

---

#### Step 8 — Interpretation

**Agent:** Experiment Advisor Agent

* Estimates acceleration
* Compares to expected physical constants
* Highlights experimental limitations

---

#### Step 9 — Report Generation

**Agent:** Report Writer Agent

Produces a structured report containing:

* Hypothesis
* Method
* Results
* Interpretation
* Limitations

---

#### Step 10 — Review and Iteration

* Human reviews report
* Decides whether to repeat or refine experiment
* Subsequent trials are linked via shared `experiment_id`

---

## 9. Human-in-the-Loop Design Principles

Humans are explicitly involved at:

* Experiment definition
* Segmentation validation
* Model selection override
* Final interpretation

The system assists and explains; it never silently replaces human judgment.

---

## 10. Repository Structure

```
labmind/
├── src/
│   └── agents/
│   ├── api/
│   ├── data/
│   ├── evaluation/
│   ├── flows/
│   └── ingestion/
├── tests/
├── notebooks/
├── .devcontainer/
├── pyproject.toml
├── uv.lock
└──  README.md
```

---

## 11. Evaluation & Trust

* Offline backtesting with synthetic data
* Deterministic replay via Metaflow
* Physics-based guardrails
* CI failures on metric regressions

---

## 12. Project Philosophy

LabMind is not an auto-grading system or a black-box AI. It is a **scientific assistant** that:

* Makes its reasoning explicit
* Preserves raw data
* Encourages learning from experimental imperfections
* Reflects real ML engineering best practices

---

*End of specification.*
