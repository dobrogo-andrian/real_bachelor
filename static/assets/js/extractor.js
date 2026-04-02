(function () {
  const session = window.CommentLabSession;
  const analysisResultsSection = document.getElementById('analysis-results');
  const analysisStatusText = document.getElementById('analysis-status-text');
  const analysisResultOutput = document.getElementById('analysis-result-output');
  const processingFilters = document.querySelector('.processing-filters');
  const processingPageNameInput = document.getElementById('processing_page_name');
  const processingPageIdInput = document.getElementById('processing_page_id');
  const processingPageNameField = document.getElementById('processing_page_name_field');
  const processingPageIdField = document.getElementById('processing_page_id_field');
  const processingSubmitButton = document.getElementById('processing_submit');
  const processingHintBox = document.getElementById('processing_hint_box');
  const processingHintText = document.getElementById('processing_hint_text');
  const manualLoginUsername = document.getElementById('manual-login-username');
  const manualLoginPasswordHint = document.getElementById('manual-login-password-hint');
  const processingButtons = [
    document.getElementById('analyze_page_name'),
    document.getElementById('analyze_page_id'),
    document.getElementById('analyze_whole_db'),
    document.getElementById('analyze_delta'),
  ];
  const extractionButtons = [
    document.getElementById('start_execution'),
    document.getElementById('start_headless_execution'),
  ];
  let processingDimensions = null;
  let pendingAnalysisMode = null;
  let pendingAnalysisLabel = null;
  let extractionInProgress = false;

  async function loadManualLoginHint() {
    try {
      const rawResponse = await session.fetchWithCsrf('/api/account/manual-login-hint', {
        method: 'GET',
        headers: {
          Accept: 'application/json',
        },
      });

      const response = await session.ensureAuthenticatedResponse(rawResponse);
      if (!response) {
        return;
      }

      const data = await response.json();
      if (!response.ok) {
        manualLoginUsername.textContent = data.error || 'Not available';
        manualLoginPasswordHint.textContent = 'Not available';
        return;
      }

      manualLoginUsername.textContent = data.instagram_login || 'Not configured';
      manualLoginPasswordHint.textContent = data.instagram_password_hint || 'Not configured';
    } catch (error) {
      manualLoginUsername.textContent = 'Not available';
      manualLoginPasswordHint.textContent = 'Not available';
    }
  }

  function setProcessingButtonsDisabled(disabled) {
    processingButtons.forEach((button) => {
      button.disabled = disabled;
    });
    processingSubmitButton.disabled = disabled;
  }

  function setExtractionButtonsDisabled(disabled) {
    extractionButtons.forEach((button) => {
      if (button) {
        button.disabled = disabled;
      }
    });
  }

  function setExtractionInProgress(active) {
    extractionInProgress = active;
    setExtractionButtonsDisabled(active);
    setProcessingButtonsDisabled(active);
  }

  async function pollJob(jobId) {
    while (true) {
      const rawResponse = await session.fetchWithCsrf(`/jobs/${jobId}`, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
        },
      });

      const response = await session.ensureAuthenticatedResponse(rawResponse);
      if (!response) {
        return null;
      }

      const job = await response.json();
      if (!response.ok) {
        throw new Error(job.error || 'Failed to fetch job status.');
      }

      if (job.status === 'completed') {
        return job.result;
      }

      if (job.status === 'failed') {
        throw new Error(job.error || 'Background job failed.');
      }

      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
  }

  async function parseApiResult(response) {
    const responseData = await response.json();
    if (response.status === 202 && responseData.job_id) {
      return pollJob(responseData.job_id);
    }
    return responseData;
  }

  function unpackJobResult(data) {
    if (Array.isArray(data) && data.length >= 1) {
      return {
        payload: data[0],
        statusCode: data.length > 1 ? data[1] : 200,
      };
    }

    return {
      payload: data,
      statusCode: 200,
    };
  }

  function scrollToAnalysisResults() {
    analysisResultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function hideProcessingFilters() {
    processingFilters.classList.remove('is-visible');
    processingPageNameField.classList.remove('is-visible');
    processingPageIdField.classList.remove('is-visible');
    processingPageNameInput.value = '';
    processingPageIdInput.value = '';
    processingHintBox.hidden = true;
    pendingAnalysisMode = null;
    pendingAnalysisLabel = null;
  }

  async function loadProcessingDimensions() {
    if (processingDimensions) {
      return processingDimensions;
    }

    const rawResponse = await session.fetchWithCsrf('/api/extractor/page-dimensions', {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    });

    const response = await session.ensureAuthenticatedResponse(rawResponse);
    if (!response) {
      return null;
    }

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Failed to load page dimensions.');
    }

    processingDimensions = data;
    return processingDimensions;
  }

  async function showProcessingHint(mode) {
    if (mode !== 'page_name' && mode !== 'page_id') {
      processingHintBox.hidden = true;
      processingHintText.textContent =
        'Select a page-level processing option to load distinct page names or page IDs from the database.';
      return;
    }

    processingHintBox.hidden = false;
    processingHintText.textContent = `Loading distinct ${mode === 'page_name' ? 'page names' : 'page IDs'}...`;

    try {
      const dimensions = await loadProcessingDimensions();
      if (!dimensions) {
        return;
      }

      const values = mode === 'page_name' ? (dimensions.page_names || []) : (dimensions.page_ids || []);
      if (!values.length) {
        processingHintText.textContent = `No distinct ${mode === 'page_name' ? 'page names' : 'page IDs'} found in the database yet.`;
        return;
      }

      processingHintText.textContent = `Distinct ${mode === 'page_name' ? 'page names' : 'page IDs'}: ${values.join(', ')}`;
    } catch (error) {
      processingHintText.textContent = error.message;
    }
  }

  async function showProcessingFilters(mode, optionLabel) {
    const isSameModeVisible =
      processingFilters.classList.contains('is-visible') &&
      pendingAnalysisMode === mode;

    if (isSameModeVisible) {
      hideProcessingFilters();
      return;
    }

    pendingAnalysisMode = mode;
    pendingAnalysisLabel = optionLabel;
    processingFilters.classList.add('is-visible');
    processingPageNameField.classList.toggle('is-visible', mode === 'page_name');
    processingPageIdField.classList.toggle('is-visible', mode === 'page_id');

    if (mode === 'page_name') {
      processingPageIdInput.value = '';
      processingPageNameInput.focus();
    } else {
      processingPageNameInput.value = '';
      processingPageIdInput.focus();
    }

    await showProcessingHint(mode);
  }

  async function runAnalysis(mode, optionLabel) {
    if (extractionInProgress) {
      analysisStatusText.textContent = 'Wait until post loading finishes before running enrichment.';
      analysisResultOutput.textContent = 'Extraction is still running.';
      scrollToAnalysisResults();
      return;
    }

    const payload = {
      mode: mode,
      page_name: processingPageNameInput.value.trim(),
      page_id: processingPageIdInput.value.trim(),
    };

    analysisStatusText.textContent = `we analysing ${optionLabel} please wait`;
    analysisResultOutput.textContent = 'Processing...';
    scrollToAnalysisResults();
    setProcessingButtonsDisabled(true);

    try {
      const rawResponse = await session.fetchWithCsrf('/enrich-comments', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const response = await session.ensureAuthenticatedResponse(rawResponse);
      if (!response) {
        return;
      }

      const responseData = await parseApiResult(response);
      const result = unpackJobResult(responseData);
      if (result.statusCode >= 400 || !result.payload || result.payload.success === false) {
        throw new Error((result.payload && result.payload.error) || 'Failed to run enrichment.');
      }

      analysisStatusText.textContent = `Analysis completed for ${optionLabel}.`;
      analysisResultOutput.textContent = JSON.stringify(result.payload.result, null, 2);
    } catch (error) {
      analysisStatusText.textContent = `Analysis failed for ${optionLabel}.`;
      analysisResultOutput.textContent = error.message;
    } finally {
      setProcessingButtonsDisabled(false);
    }
  }

  async function runExtraction(headlessSessionOnly) {
    setExtractionInProgress(true);
    const param1 = document.getElementById('instagram_page').value;
    const param2 = document.getElementById('number_of_posts').value;
    const payload = {
      params: {
        param1: param1,
        param2: param2,
        headless_session_only: headlessSessionOnly,
      },
    };

    try {
      const rawResponse = await session.fetchWithCsrf('/process-data', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const response = await session.ensureAuthenticatedResponse(rawResponse);
      if (!response) {
        return;
      }

      const data = await parseApiResult(response);
      const result = unpackJobResult(data);

      if (result.statusCode < 400 && result.payload && result.payload.success) {
        document.getElementById('response-p').textContent = [
          `Target page: ${result.payload.result.target_page}`,
          `Posts requested: ${result.payload.result.posts_requested}`,
          `Posts successfully loaded: ${result.payload.result.posts_loaded}`,
          `Comments collected: ${result.payload.result.comments_collected}`,
          `Rows loaded into DB: ${result.payload.result.rows_loaded_to_db}`,
          `CSV files processed: ${result.payload.result.files_processed}`,
        ].join('\n');
      } else {
        document.getElementById('response-p').textContent = `Error: ${(result.payload && result.payload.error) || 'Process-data request failed.'}`;
      }
    } catch (error) {
      document.getElementById('response-p').textContent = `Error: ${error.message}`;
    } finally {
      setExtractionInProgress(false);
    }
  }

  document.getElementById('analyze_page_name').addEventListener('click', () => {
    showProcessingFilters('page_name', 'page name');
  });

  document.getElementById('analyze_page_id').addEventListener('click', () => {
    showProcessingFilters('page_id', 'page id');
  });

  document.getElementById('analyze_whole_db').addEventListener('click', () => {
    hideProcessingFilters();
    showProcessingHint('whole_db');
    runAnalysis('whole_db', 'whole db');
  });

  document.getElementById('analyze_delta').addEventListener('click', () => {
    hideProcessingFilters();
    showProcessingHint('delta');
    runAnalysis('delta', 'delta');
  });

  processingSubmitButton.addEventListener('click', () => {
    if (!pendingAnalysisMode) {
      return;
    }

    runAnalysis(pendingAnalysisMode, pendingAnalysisLabel);
    hideProcessingFilters();
  });

  document.getElementById('start_execution').addEventListener('click', async () => {
    runExtraction(false);
  });

  document.getElementById('start_headless_execution').addEventListener('click', async () => {
    runExtraction(true);
  });

  loadManualLoginHint();
})();
