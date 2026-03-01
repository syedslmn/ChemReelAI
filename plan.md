# Chemistry Lab Video Generator — Implementation Plan

## Current Status

> **Last updated:** 2026-03-01
>
> **Overall:** Node 1 (Nova Pro text generation) and Node 3 (S3 presigned URL) work.
> **Blocker:** Node 2 — Nova Reel clip generation is failing at runtime. The call to
> `bedrock.start_async_invoke(modelId="amazon.nova-reel-v1:0", ...)` returns an error.
> This needs debugging (check model access, region, payload format, IAM permissions).

---

## Implementation Checklist

### Spring Boot (`sb-app/`) — ALL COMPLETE

- [x] `config/AppConfig.java` — RestTemplate bean
- [x] `controller/ExperimentController.java` — `POST /api/experiment`, `GET /api/status/{jobId}`
- [x] `service/ExperimentService.java` — delegates to PythonClient
- [x] `helper/PythonClient.java` — RestTemplate calls to Python FastAPI
- [x] `model/ExperimentRequest.java` — request DTO
- [x] `model/JobResponse.java` — `@JsonProperty("job_id")` DTO
- [x] `model/StatusResponse.java` — `@JsonProperty` for `video_url`, `error_message`
- [x] `resources/application.yaml` — `server.port=8080`, `python.service.url=http://localhost:5000`
- [x] `resources/static/index.html` — styled UI with example chips, video player
- [x] `resources/static/css/style.css` — full styling
- [x] `resources/static/js/app.js` — form submit, polling, video display
- [x] SLF4J info + error logging in `ExperimentController` and `PythonClient`
- [x] JAR built: `target/sb-app-1.0.0-SNAPSHOT.jar`

### Python (`py-app/`) — CODE COMPLETE, RUNTIME ERROR IN NODE 2

- [x] `requirements.txt` — fastapi, uvicorn, langgraph, boto3, python-dotenv
- [x] `.env` — AWS credentials configured
- [x] `main.py` — FastAPI app, `/generate` (202), `/status/{job_id}`, threading, logging
- [x] `agent/state.py` — `ExperimentState` TypedDict
- [x] `agent/graph.py` — LangGraph StateGraph with conditional error edges
- [x] `agent/nodes/clients.py` — boto3 `bedrock-runtime` + `s3` clients, constants
- [x] `agent/nodes/generate_procedure.py` — Node 1: Nova Pro → JSON step array (WORKING)
- [ ] `agent/nodes/generate_clips.py` — Node 2: Nova Reel async invoke + ffmpeg concat (**FAILING — runtime error calling Nova Reel**)
- [x] `agent/nodes/generate_presigned_url.py` — Node 3: S3 presigned URL generation (code complete)
- [x] Python `logging` module wired in `main.py` and all three node files

---

## Context
Build a two-process system to help 12th-grade students understand chemistry lab experiments. The student types one line describing an experiment; the system generates a step-by-step video using Amazon Bedrock (Nova Pro for text, Nova Reel for video) and presents it in the browser.

---

## Architecture

```
Browser (index.html @ :8080)
    POST /api/experiment  →  Spring Boot :8080  →  POST Python :5000/generate
    GET  /api/status/{id} →  Spring Boot :8080  →  GET  Python :5000/status/{id}
                                                         |
                                              LangGraph Agent (3 nodes)
                                              Node 1: Bedrock Nova Pro → steps[]
                                              Node 2: Bedrock Nova Reel → clips + ffmpeg
                                              Node 3: S3 presigned URL
```

---

## Deviation from Original Plan

The original plan described Nova Reel as a **synchronous** `invoke_model` call returning base64 video.
The actual implementation correctly uses the **asynchronous** API:
- `bedrock.start_async_invoke(...)` — starts the job, output goes to S3
- `bedrock.get_async_invoke(invocationArn=...)` — polls until Completed/Failed
- `s3.download_file(...)` — downloads clip from S3 to local temp dir

State fields were updated accordingly:
- `clip_paths` → `clip_s3_keys`
- `final_video_path` → `final_video_key`

---

## Java Class Designs

### `AppConfig.java`
```java
@Configuration
public class AppConfig {
    @Bean
    public RestTemplate restTemplate() { return new RestTemplate(); }
}
```

### `model/ExperimentRequest.java`
```java
// Received FROM browser
public class ExperimentRequest {
    private String experimentName;   // camelCase, browser sends {"experimentName":"..."}
    // default constructor + getter/setter
}
```

### `model/JobResponse.java`
```java
// Received FROM Python (snake_case) + sent TO browser
public class JobResponse {
    @JsonProperty("job_id")   // handles Python's "job_id" in/out
    private String jobId;
    // default constructor + getter/setter
}
```
Browser JS reads `data.job_id`.

### `model/StatusResponse.java`
```java
public class StatusResponse {
    private String status;                        // "pending"|"processing"|"completed"|"failed"

    @JsonProperty("video_url")
    private String videoUrl;

    @JsonProperty("error_message")
    private String errorMessage;
    // default constructor + getters/setters
}
```
Browser JS reads `data.status`, `data.video_url`, `data.error_message`.

### `PythonClient.java`
```java
@Service
public class PythonClient {
    // Injects RestTemplate + @Value("${python.service.url}") String pythonBaseUrl
    // SLF4J Logger for info + error logging

    public JobResponse submitExperiment(String experimentName) {
        // POST {baseUrl}/generate with body Map.of("experiment_name", experimentName)
        // Returns JobResponse
    }

    public StatusResponse getStatus(String jobId) {
        // GET {baseUrl}/status/{jobId}
        // Returns StatusResponse
    }
}
```

### `ExperimentController.java`
```java
@RestController
@RequestMapping("/api")
public class ExperimentController {
    // Injects ExperimentService
    // SLF4J Logger for info + error logging

    @PostMapping("/experiment")
    public JobResponse submit(@RequestBody ExperimentRequest req)
    // Logs request + response, returns JobResponse

    @GetMapping("/status/{jobId}")
    public StatusResponse status(@PathVariable String jobId)
    // Logs request + response, returns StatusResponse
}
```

---

## application.yaml
```yaml
spring:
  application:
    name: sb-app
server:
  port: 8080
python:
  service:
    url: http://localhost:5000
```

---

## Python Structure

### `requirements.txt`
```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
langgraph>=0.2.0
boto3>=1.34.84
python-dotenv>=1.0.1
```

### `agent/state.py` — `ExperimentState` TypedDict
```python
class ExperimentState(TypedDict):
    experiment_name:    str           # set at init
    procedure_steps:    list[str]     # written by Node 1
    clip_s3_keys:       list[str]     # written by Node 2
    final_video_key:    Optional[str] # written by Node 2
    video_url:          Optional[str] # written by Node 3
    error:              Optional[str] # set by any node on failure
```

### `agent/nodes/` — Three node functions (separate files)

**Node 1 `generate_procedure(state)` — WORKING**
- Calls `bedrock.invoke_model(modelId="amazon.nova-pro-v1:0")`
- Prompt asks Nova Pro to return a JSON array of ≤8 concise step strings
- Returns `{"procedure_steps": [...]}` or `{"error": "..."}` on failure

**Node 2 `generate_clips(state)` — FAILING AT RUNTIME**
- For each step, calls `bedrock.start_async_invoke(modelId="amazon.nova-reel-v1:0")` with:
  ```json
  {"taskType":"TEXT_VIDEO","textToVideoParams":{"text":"<step>"},"videoGenerationConfig":{"durationSeconds":6,"fps":24,"dimension":"1280x720","seed":<i>}}
  ```
- Polls `bedrock.get_async_invoke(invocationArn=...)` every 15s until Completed/Failed
- Downloads each clip from S3, concatenates with ffmpeg, uploads final video to S3
- Returns `{"clip_s3_keys":[...],"final_video_key":"..."}` or `{"error":"..."}`
- **STATUS: Error occurs when calling Nova Reel — needs investigation**

**Node 3 `generate_presigned_url(state)` — CODE COMPLETE**
- `s3.generate_presigned_url("get_object", ..., ExpiresIn=3600)`
- Returns `{"video_url": "https://..."}` or `{"error":"..."}`

### `agent/graph.py` — LangGraph StateGraph
```
START → generate_procedure
generate_procedure --[error?]--> END
generate_procedure --[ok]--> generate_clips
generate_clips --[error?]--> END
generate_clips --[ok]--> generate_presigned_url
generate_presigned_url → END
```
Uses `add_conditional_edges` with lambda checking `state.get("error")`.

### `main.py` — FastAPI app
- `POST /generate` → creates UUID job_id, sets `_jobs[job_id] = {status:"pending"}`, starts `threading.Thread(target=_run_agent)`, returns `{job_id}`
- `GET /status/{job_id}` → returns `_jobs[job_id]` or 404
- `_run_agent(job_id, experiment_name)` → marks "processing", calls `chemistry_graph.invoke(initial_state)`, sets "completed"/"failed"

---

## HTML Page (`static/index.html`)
- Styled card layout: title, subtitle, text input, submit button, example chips
- On submit: `POST /api/experiment` → get `job_id` → poll `GET /api/status/{job_id}` every 4s
- Show status messages (pending/processing/completed/failed)
- On completed: show `<video controls src="{data.video_url}">`
- Note: reads `data.job_id`, `data.video_url`, `data.error_message` (snake_case from Java `@JsonProperty`)

---

## Environment Variables (Python)
```bash
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION, S3_BUCKET_NAME
```

---

## Startup
```bash
# Terminal 1
cd py-app && pip install -r requirements.txt
python main.py        # FastAPI on :5000

# Terminal 2
cd sb-app && java -jar target/sb-app-1.0.0-SNAPSHOT.jar   # Spring Boot on :8080
```
Visit `http://localhost:8080`

---

## S3 CORS Note
Add a CORS rule to the S3 bucket allowing `GET` from `http://localhost:8080` so the browser can load the presigned video URL.
