# Architecture — Chemistry Lab Video Generator

## Overview

A two-process system serving 12th-grade students. The student describes a chemistry experiment in one line; the system generates a narrated, step-by-step video using Amazon Bedrock and returns it in the browser.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          STUDENT'S BROWSER                              │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  index.html (served from Spring Boot static/)                   │   │
│   │                                                                 │   │
│   │  [Text Input] "Titration of HCl with NaOH"  [Generate Video]   │   │
│   │                                                                 │   │
│   │  Status: "Generating your lab video..."                         │   │
│   │                                                                 │   │
│   │  ┌──────────────────────────────────────┐                       │   │
│   │  │          <video> player              │                       │   │
│   │  └──────────────────────────────────────┘                       │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│       │  POST /api/experiment  {"experimentName":"..."}                  │
│       │  GET  /api/status/{jobId}   (polls every 4s)                    │
└───────┼─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    SPRING BOOT APP  (port 8080)                        │
│                    sb-app  ·  Java 21  ·  Spring Boot 3.2.0           │
│                                                                        │
│  ┌──────────────────────┐      ┌──────────────────────────────────┐   │
│  │  ExperimentController│      │          PythonClient            │   │
│  │                      │      │                                  │   │
│  │  POST /api/experiment│─────▶│  POST http://localhost:5000      │   │
│  │  → 202 + {job_id}    │      │       /generate                  │   │
│  │                      │      │                                  │   │
│  │  GET /api/status/    │─────▶│  GET  http://localhost:5000      │   │
│  │      {jobId}         │      │       /status/{job_id}           │   │
│  │  → 200 + StatusResp  │      │                                  │   │
│  └──────────────────────┘      └──────────────────────────────────┘   │
│                                           │                            │
│  ┌──────────────────────┐                 │  RestTemplate (HTTP)       │
│  │  AppConfig           │                 │                            │
│  │  └─ RestTemplate bean│                 │                            │
│  └──────────────────────┘                 │                            │
│                                           │                            │
│  Model DTOs:                              │                            │
│   ExperimentRequest  {experimentName}     │                            │
│   JobResponse        {job_id}             │                            │
│   StatusResponse     {status,             │                            │
│                       video_url,          │                            │
│                       error_message}      │                            │
└───────────────────────────────────────────┼────────────────────────────┘
                                            │  HTTP REST
                                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                  PYTHON FastAPI SERVICE  (port 5000)                   │
│                  py-app  ·  Python  ·  FastAPI + uvicorn               │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │  main.py                                                        │   │
│  │                                                                 │   │
│  │  POST /generate                                                 │   │
│  │    → create job_id (UUID)                                       │   │
│  │    → _jobs[job_id] = {status: "pending"}                        │   │
│  │    → spawn daemon Thread(_run_agent)                            │   │
│  │    → return {job_id}  immediately (202)                         │   │
│  │                                                                 │   │
│  │  GET /status/{job_id}                                           │   │
│  │    → return _jobs[job_id]  (or 404)                             │   │
│  └────────────────────┬────────────────────────────────────────────┘   │
│                       │  background thread                             │
│                       ▼                                                │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │  LangGraph Agent  (agent/)                                      │   │
│  │                                                                 │   │
│  │  State: ExperimentState                                         │   │
│  │  ┌─────────────────┐                                            │   │
│  │  │ experiment_name │  ← set at init                             │   │
│  │  │ procedure_steps │  ← written by Node 1                       │   │
│  │  │ clip_paths      │  ← written by Node 2                       │   │
│  │  │ final_video_path│  ← written by Node 2                       │   │
│  │  │ video_url       │  ← written by Node 3                       │   │
│  │  │ error           │  ← set by any node on failure              │   │
│  │  └─────────────────┘                                            │   │
│  │                                                                 │   │
│  │  ┌──────────────────────────────────────────────────────────┐   │   │
│  │  │                   Graph Flow                             │   │   │
│  │  │                                                          │   │   │
│  │  │  START                                                   │   │   │
│  │  │    │                                                     │   │   │
│  │  │    ▼                                                     │   │   │
│  │  │  [Node 1: generate_procedure] ──error?──▶ END            │   │   │
│  │  │    │ ok                                                  │   │   │
│  │  │    ▼                                                     │   │   │
│  │  │  [Node 2: generate_clips]     ──error?──▶ END            │   │   │
│  │  │    │ ok                                                  │   │   │
│  │  │    ▼                                                     │   │   │
│  │  │  [Node 3: upload_to_s3]                                  │   │   │
│  │  │    │                                                     │   │   │
│  │  │    ▼                                                     │   │   │
│  │  │   END                                                    │   │   │
│  │  └──────────────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────────┘   │
└────────────────────────┬──────────────────────────┬───────────────────┘
                         │                          │
                         ▼                          ▼
          ┌──────────────────────┐     ┌────────────────────────┐
          │  AWS BEDROCK         │     │  AWS S3                │
          │                      │     │                        │
          │  Nova Pro            │     │  Bucket:               │
          │  amazon.nova-pro-v1  │     │  nova-hackathon-videos │
          │  ─────────────────── │     │                        │
          │  Input:              │     │  Key:                  │
          │    experiment name   │     │  experiments/{uuid}/   │
          │  Output:             │     │    final_video.mp4     │
          │    steps[] (JSON arr)│     │                        │
          │                      │     │  Returns:              │
          │  Nova Reel           │     │  presigned URL (1 hr)  │
          │  amazon.nova-reel-v1 │     └────────────────────────┘
          │  ─────────────────── │
          │  Input (per step):   │
          │    text, 6s, 1280x720│
          │  Output:             │
          │    base64 mp4 clip   │
          │                      │
          │  + ffmpeg concat     │
          │    clip_00..clip_N   │
          │    → final_video.mp4 │
          └──────────────────────┘
```

---

## Request / Response Flow

```
Student types experiment
        │
        │  1. POST /api/experiment
        │     {"experimentName": "Titration of HCl with NaOH"}
        ▼
Spring Boot (ExperimentController)
        │
        │  2. POST http://localhost:5000/generate
        │     {"experiment_name": "Titration of HCl with NaOH"}
        ▼
FastAPI (main.py)
        │
        │  3. Returns {"job_id": "uuid"} → Spring Boot → Browser
        │     (job runs in background thread)
        │
        │  ┌─────────────────────────────────────────┐
        │  │  Background Thread: _run_agent()         │
        │  │                                          │
        │  │  Node 1: Nova Pro                        │
        │  │    → ["Step 1...", "Step 2...", ...]     │
        │  │                                          │
        │  │  Node 2: Nova Reel × N steps             │
        │  │    → clip_00.mp4, clip_01.mp4, ...       │
        │  │    → ffmpeg concat → final_video.mp4     │
        │  │                                          │
        │  │  Node 3: S3 upload                       │
        │  │    → presigned URL                       │
        │  └─────────────────────────────────────────┘
        │
        │  4. Browser polls GET /api/status/{jobId}  (every 4s)
        │     Spring Boot → GET http://localhost:5000/status/{job_id}
        │     Returns: {"status": "pending"|"processing"|"completed"|"failed",
        │               "video_url": "...",
        │               "error_message": "..."}
        │
        │  5. On "completed" → browser shows <video src="{video_url}">
        ▼
Student watches the lab video
```

---

## Job Status State Machine

```
             ┌─────────┐
   submit ──▶│ pending │
             └────┬────┘
                  │ thread starts
                  ▼
           ┌────────────┐
           │ processing │
           └─────┬──────┘
                 │
        ┌────────┴─────────┐
        │                  │
        ▼                  ▼
  ┌───────────┐      ┌────────┐
  │ completed │      │ failed │
  └───────────┘      └────────┘
```

---

## Component Responsibilities

| Component | Technology | Responsibility |
|-----------|-----------|----------------|
| Browser | HTML + Vanilla JS | Input form, polling, video display |
| Spring Boot | Java 21, Spring Boot 3.2.0 | Static file serving, REST API gateway, delegates to Python |
| FastAPI | Python, FastAPI, uvicorn | Job queue, background runner, Bedrock/S3 orchestration |
| LangGraph Agent | LangChain, LangGraph | 3-node directed graph: text → clips → S3 |
| Amazon Bedrock Nova Pro | `amazon.nova-pro-v1:0` | Generate step-by-step experiment procedure |
| Amazon Bedrock Nova Reel | `amazon.nova-reel-v1:0` | Generate 6-second video clip per step |
| ffmpeg | CLI tool | Concatenate per-step clips into one final video |
| Amazon S3 | AWS S3 | Store final video, serve via presigned URL |

---

## Port Map

| Service | Port | Notes |
|---------|------|-------|
| Spring Boot | 8080 | Browser-facing; serves HTML + REST API |
| Python FastAPI | 5000 | Internal only; called by Spring Boot |
| AWS Bedrock | — | AWS-managed endpoint; called by Python via boto3 |
| AWS S3 | — | AWS-managed; presigned URL served directly to browser |

---

## Project File Structure

```
Nova-Hackathon/
├── plan.md                          ← implementation plan
├── architecture.md                  ← this file
│
├── sb-app/                          ← Spring Boot module (Java 21)
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/nova/sbapp/
│       │   ├── SbAppApplication.java
│       │   ├── AppConfig.java           ← RestTemplate bean
│       │   ├── ExperimentController.java← POST /api/experiment, GET /api/status
│       │   ├── PythonClient.java        ← HTTP calls to FastAPI
│       │   └── model/
│       │       ├── ExperimentRequest.java
│       │       ├── JobResponse.java
│       │       └── StatusResponse.java
│       └── resources/
│           ├── application.properties
│           └── static/
│               └── index.html           ← student UI
│
└── py-app/                          ← Python FastAPI service
    ├── requirements.txt
    ├── .env.example
    ├── main.py                      ← FastAPI app + job store + thread runner
    └── agent/
        ├── __init__.py
        ├── state.py                 ← ExperimentState TypedDict
        ├── nodes.py                 ← Node 1 (Nova Pro), Node 2 (Nova Reel+ffmpeg), Node 3 (S3)
        └── graph.py                 ← LangGraph StateGraph + conditional edges
```

---

## AWS Services Used

```
┌─────────────────────────────────────────────────────┐
│                   AWS Account                        │
│                                                      │
│  ┌─────────────────────┐   ┌──────────────────────┐  │
│  │   Amazon Bedrock     │   │      Amazon S3       │  │
│  │                      │   │                      │  │
│  │  ┌───────────────┐   │   │  nova-hackathon-     │  │
│  │  │  Nova Pro     │   │   │  videos/             │  │
│  │  │  (text gen)   │   │   │                      │  │
│  │  └───────────────┘   │   │  experiments/        │  │
│  │                      │   │  └─ {uuid}/          │  │
│  │  ┌───────────────┐   │   │     └─ final_video   │  │
│  │  │  Nova Reel    │   │   │        .mp4          │  │
│  │  │  (video gen)  │   │   │                      │  │
│  │  └───────────────┘   │   │  CORS: allow GET     │  │
│  │                      │   │  from :8080          │  │
│  └─────────────────────┘   └──────────────────────┘  │
│                                                      │
│  Auth: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY     │
│  Region: AWS_DEFAULT_REGION (e.g. us-east-1)         │
└─────────────────────────────────────────────────────┘
```
