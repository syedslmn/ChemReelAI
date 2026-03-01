package com.nova.sbapp.helper;

import com.nova.sbapp.model.JobResponse;
import com.nova.sbapp.model.StatusResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

@Service
public class PythonClient {

    private static final Logger log = LoggerFactory.getLogger(PythonClient.class);

    private final RestTemplate restTemplate;
    private final String pythonBaseUrl;

    @Autowired
    public PythonClient(RestTemplate restTemplate,
                        @Value("${python.service.url}") String pythonBaseUrl) {
        this.restTemplate = restTemplate;
        this.pythonBaseUrl = pythonBaseUrl;
    }

    public JobResponse submitExperiment(String experimentName) {
        String url = pythonBaseUrl + "/generate";

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        Map<String, String> body = Map.of("experiment_name", experimentName);
        HttpEntity<Map<String, String>> request = new HttpEntity<>(body, headers);

        log.info("Calling Python service POST {} for experiment: '{}'", url, experimentName);
        try {
            ResponseEntity<JobResponse> response =
                    restTemplate.postForEntity(url, request, JobResponse.class);
            log.info("Python service accepted experiment '{}' — job_id: {}",
                    experimentName, response.getBody() != null ? response.getBody().getJobId() : "null");
            return response.getBody();
        } catch (Exception e) {
            log.error("Failed to submit experiment '{}' to Python service at {}: {}",
                    experimentName, url, e.getMessage(), e);
            throw e;
        }
    }

    public StatusResponse getStatus(String jobId) {
        String url = pythonBaseUrl + "/status/" + jobId;

        log.info("Polling Python service GET {} for job status", url);
        try {
            ResponseEntity<StatusResponse> response =
                    restTemplate.getForEntity(url, StatusResponse.class);
            log.info("Status for job '{}': {}",
                    jobId, response.getBody() != null ? response.getBody().getStatus() : "null");
            return response.getBody();
        } catch (Exception e) {
            log.error("Failed to fetch status for job '{}' from Python service at {}: {}",
                    jobId, url, e.getMessage(), e);
            throw e;
        }
    }
}
