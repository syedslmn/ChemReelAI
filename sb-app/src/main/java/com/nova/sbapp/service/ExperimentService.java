package com.nova.sbapp.service;

import com.nova.sbapp.helper.PythonClient;
import com.nova.sbapp.model.JobResponse;
import com.nova.sbapp.model.StatusResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class ExperimentService {

    private final PythonClient pythonClient;

    @Autowired
    public ExperimentService(PythonClient pythonClient) {
        this.pythonClient = pythonClient;
    }

    public JobResponse submitExperiment(String experimentName) {
        return pythonClient.submitExperiment(experimentName);
    }

    public StatusResponse getStatus(String jobId) {
        return pythonClient.getStatus(jobId);
    }
}
