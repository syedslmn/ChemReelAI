# ChemLab AI — Class 12 Chemistry Visual Lab Assistant

An AI-powered web application that helps Class 12 students understand chemistry lab experiments through auto-generated step-by-step videos. A student types one line describing an experiment and receives a full video walkthrough powered by Amazon Bedrock.

---

## How It Works

```
Student types experiment name
        ↓
Spring Boot (port 8080) — serves UI, exposes REST API
        ↓
Python FastAPI (port 5000) — runs LangGraph agent
        ↓
Node 1: Amazon Bedrock Nova Pro  → generates procedure steps
Node 2: Amazon Bedrock Nova Reel → generates 6s video per step → ffmpeg concat
Node 3: Amazon S3                → stores final video, returns presigned URL
        ↓
Video plays in the student's browser
```

---

## Project Structure

```
Nova-Hackathon/
├── sb-app/                         # Spring Boot application (Java 21)
│   └── src/main/
│       ├── java/com/nova/sbapp/
│       │   ├── SbAppApplication.java
│       │   ├── config/
│       │   │   └── AppConfig.java          # RestTemplate bean
│       │   ├── controller/
│       │   │   └── ExperimentController.java
│       │   ├── service/
│       │   │   └── ExperimentService.java
│       │   ├── helper/
│       │   │   └── PythonClient.java       # HTTP client for Python service
│       │   └── model/
│       │       ├── ExperimentRequest.java
│       │       ├── JobResponse.java
│       │       └── StatusResponse.java
│       └── resources/
│           ├── application.yaml
│           └── static/
│               ├── index.html
│               ├── css/style.css
│               └── js/app.js
│
└── py-app/                         # Python FastAPI + LangGraph agent
    ├── main.py                     # FastAPI app, job store, background runner
    ├── requirements.txt
    ├── .env.example
    └── agent/
        ├── state.py                # ExperimentState TypedDict
        ├── graph.py                # LangGraph StateGraph
        └── nodes/
            ├── clients.py                  # Shared boto3 clients
            ├── generate_procedure.py       # Node 1 — Nova Pro
            ├── generate_clips.py           # Node 2 — Nova Reel + ffmpeg
            └── generate_presigned_url.py   # Node 3 — S3 presigned URL
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Java | 21 |
| Maven | 3.8+ |
| Python | 3.14+ |
| ffmpeg | any recent |
| AWS account | with Bedrock Nova Pro, Nova Reel, and S3 access |

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd Nova-Hackathon
```

### 2. Configure AWS credentials

```bash
cp py-app/.env.example py-app/.env
```

Edit `py-app/.env`:

```bash
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_SESSION_TOKEN=your_session_token_here_if_using_temporary_credentials
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name-here
```

> If you have `~/.aws/credentials` configured, boto3 will pick it up automatically and the `.env` file is optional.

### 3. Install Python dependencies

```bash
cd py-app
pip install -r requirements.txt
```

### 4. Install ffmpeg

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

### 5. Create an S3 bucket

Create a bucket in your AWS account and set its name in `.env`. Add a CORS rule to allow the browser to load presigned video URLs:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET"],
    "AllowedOrigins": ["http://localhost:8080"],
    "ExposeHeaders": []
  }
]
```

---

## Running the App

Open two terminals.

**Terminal 1 — Python agent service (port 5000)**

```bash
cd py-app
python main.py
```

**Terminal 2 — Spring Boot UI server (port 8080)**

```bash
cd sb-app
mvn spring-boot:run
```

Open your browser at **http://localhost:8080**

---

## API Reference

### Spring Boot (port 8080)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/experiment` | Submit an experiment, returns `job_id` |
| `GET` | `/api/status/{jobId}` | Poll job status |

**POST /api/experiment**
```json
// Request
{ "experimentName": "Titration of HCl with NaOH" }

// Response 202
{ "job_id": "a3f2c1d0-..." }
```

**GET /api/status/{jobId}**
```json
// Pending / processing
{ "status": "pending", "video_url": null, "error_message": null }

// Completed
{ "status": "completed", "video_url": "https://s3.amazonaws.com/...", "error_message": null }

// Failed
{ "status": "failed", "video_url": null, "error_message": "reason" }
```

### Python FastAPI (port 5000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/generate` | Start agent job, returns `job_id` |
| `GET` | `/status/{job_id}` | Return job status |

Interactive API docs available at **http://localhost:5000/docs**

---

## LangGraph Agent

The agent runs as a directed graph with three nodes and error short-circuit edges:

```
START
  └─→ generate_procedure   (Nova Pro — produces step list)
        ├─→ [error] → END
        └─→ generate_clips  (Nova Reel per step + ffmpeg concat)
              ├─→ [error] → END
              └─→ generate_presigned_url  (S3 upload + presigned URL)
                    └─→ END
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML, CSS, Vanilla JS |
| Backend | Java 21, Spring Boot 3.2 |
| Agent service | Python 3.14, FastAPI, LangGraph |
| Text generation | Amazon Bedrock Nova Pro (`amazon.nova-pro-v1:0`) |
| Video generation | Amazon Bedrock Nova Reel (`amazon.nova-reel-v1:0`) |
| Video processing | ffmpeg |
| Storage | Amazon S3 |
