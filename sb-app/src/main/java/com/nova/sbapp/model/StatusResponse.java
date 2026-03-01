package com.nova.sbapp.model;

import com.fasterxml.jackson.annotation.JsonProperty;

public class StatusResponse {

    private String status;

    @JsonProperty("video_url")
    private String videoUrl;

    @JsonProperty("error_message")
    private String errorMessage;

    public StatusResponse() {}

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getVideoUrl() {
        return videoUrl;
    }

    public void setVideoUrl(String videoUrl) {
        this.videoUrl = videoUrl;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }
}
