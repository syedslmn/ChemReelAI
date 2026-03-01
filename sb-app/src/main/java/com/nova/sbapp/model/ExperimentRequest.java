package com.nova.sbapp.model;

public class ExperimentRequest {

    private String experimentName;

    public ExperimentRequest() {}

    public ExperimentRequest(String experimentName) {
        this.experimentName = experimentName;
    }

    public String getExperimentName() {
        return experimentName;
    }

    public void setExperimentName(String experimentName) {
        this.experimentName = experimentName;
    }
}
