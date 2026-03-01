package com.nova.sbapp.model;

import com.fasterxml.jackson.annotation.JsonProperty;

public class JobResponse {

    @JsonProperty("job_id")
    private String jobId;

    public JobResponse() {}

    public JobResponse(String jobId) {
        this.jobId = jobId;
    }

    public String getJobId() {
        return jobId;
    }

    public void setJobId(String jobId) {
        this.jobId = jobId;
    }
}
