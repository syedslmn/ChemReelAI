package com.nova.sbapp.controller;

import com.nova.sbapp.model.ExperimentRequest;
import com.nova.sbapp.model.JobResponse;
import com.nova.sbapp.model.StatusResponse;
import com.nova.sbapp.service.ExperimentService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ExperimentController {

    private static final Logger log = LoggerFactory.getLogger(ExperimentController.class);

    private final ExperimentService experimentService;

    @Autowired
    public ExperimentController(ExperimentService experimentService) {
        this.experimentService = experimentService;
    }

    @PostMapping("/experiment")
    public JobResponse submitExperiment(@RequestBody ExperimentRequest request) {
        log.info("POST /api/experiment — experiment: '{}'", request.getExperimentName());
        try {
            JobResponse response = experimentService.submitExperiment(request.getExperimentName());
            log.info("Experiment '{}' queued — job_id: {}", request.getExperimentName(), response.getJobId());
            return response;
        } catch (Exception e) {
            log.error("Error submitting experiment '{}': {}", request.getExperimentName(), e.getMessage(), e);
            throw e;
        }
    }

    @GetMapping("/status/{jobId}")
    public StatusResponse getStatus(@PathVariable String jobId) {
        log.info("GET /api/status/{}", jobId);
        try {
            StatusResponse response = experimentService.getStatus(jobId);
            log.info("Status for job '{}': {}", jobId, response.getStatus());
            return response;
        } catch (Exception e) {
            log.error("Error fetching status for job '{}': {}", jobId, e.getMessage(), e);
            throw e;
        }
    }
}
