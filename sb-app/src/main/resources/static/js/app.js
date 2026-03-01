const POLL_INTERVAL_MS = 4000;
const MAX_POLLS = 150;  // 10 minutes max

const form           = document.getElementById('experiment-form');
const inputEl        = document.getElementById('experiment-input');
const submitBtn      = document.getElementById('submit-btn');
const btnLabel       = document.getElementById('btn-label');
const btnSpinner     = document.getElementById('btn-spinner');
const statusBox      = document.getElementById('status-box');
const videoContainer = document.getElementById('video-container');
const videoPlayer    = document.getElementById('video-player');

// Fill input when an example chip is clicked
document.querySelectorAll('.example-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    inputEl.value = chip.textContent;
    inputEl.focus();
  });
});

function showStatus(message, type) {
  statusBox.className = 'status-box ' + type;
  statusBox.textContent = message;
}

function setFormEnabled(enabled) {
  inputEl.disabled   = !enabled;
  submitBtn.disabled = !enabled;
  btnLabel.hidden    = !enabled;
  btnSpinner.hidden  = enabled;
}

function startPolling(jobId) {
  let pollCount = 0;

  const intervalId = setInterval(async () => {
    pollCount++;
    if (pollCount > MAX_POLLS) {
      clearInterval(intervalId);
      showStatus('Request timed out. Please try again.', 'error');
      setFormEnabled(true);
      return;
    }

    try {
      const res  = await fetch('/api/status/' + jobId);
      const data = await res.json();

      if (data.status === 'pending') {
        showStatus('Your request is queued...', 'info');
      } else if (data.status === 'processing') {
        showStatus('Generating your lab video — this may take several minutes.', 'info');
      } else if (data.status === 'completed') {
        clearInterval(intervalId);
        showStatus('Your video is ready!', 'success');
        videoPlayer.src = data.video_url;
        videoContainer.style.display = 'block';
        setFormEnabled(true);
      } else if (data.status === 'failed') {
        clearInterval(intervalId);
        showStatus('Error: ' + (data.error_message || 'Unknown error'), 'error');
        setFormEnabled(true);
      }
    } catch (err) {
      console.warn('Poll error (will retry):', err);
    }
  }, POLL_INTERVAL_MS);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  const experimentName = inputEl.value.trim();
  if (!experimentName) return;

  videoContainer.style.display = 'none';
  videoPlayer.src = '';
  setFormEnabled(false);
  showStatus('Submitting your experiment...', 'info');

  try {
    const res = await fetch('/api/experiment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ experimentName }),
    });

    if (!res.ok) throw new Error('Server returned ' + res.status);

    const data = await res.json();
    showStatus('Experiment submitted. Starting video generation...', 'info');
    startPolling(data.job_id);

  } catch (err) {
    showStatus('Failed to submit: ' + err.message, 'error');
    setFormEnabled(true);
  }
});
