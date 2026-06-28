/**
 * Thin wrapper around window.pywebview.api.
 * All calls return Promises. Retries if pywebview isn't ready yet.
 */
const api = (() => {
  function call(method, ...args) {
    return new Promise((resolve, reject) => {
      function attempt(retries) {
        if (window.pywebview && window.pywebview.api && window.pywebview.api[method]) {
          window.pywebview.api[method](...args).then(resolve).catch(reject);
        } else if (retries > 0) {
          setTimeout(() => attempt(retries - 1), 100);
        } else {
          reject(new Error(`pywebview API not ready (method: ${method})`));
        }
      }
      attempt(30);
    });
  }

  return {
    // Profiles
    listProfiles:    ()       => call('list_profiles'),
    getProfile:      (id)     => call('get_profile', id),
    saveProfile:     (data)   => call('save_profile', data),
    deleteProfile:   (id)     => call('delete_profile', id),
    newProfileId:    ()       => call('new_profile_id'),

    // Bookings
    listBookings:    ()       => call('list_bookings'),
    getBooking:      (id)     => call('get_booking', id),
    getBookingLogs:  (id)     => call('get_booking_logs', id),
    triggerBooking:  (profileId, siteId, targetDate) =>
                               call('trigger_booking', profileId, siteId, targetDate),
    cancelBooking:   (id)     => call('cancel_booking', id),

    // Schedules
    listSchedules:   ()       => call('list_schedules'),
    getSchedule:     (id)     => call('get_schedule', id),
    previewFireTime: (date)   => call('preview_fire_time', date),
    saveSchedule:    (data)   => call('save_schedule', data),
    deleteSchedule:  (id)     => call('delete_schedule', id),
    toggleSchedule:  (id, en) => call('toggle_schedule', id, en),

    // Sources
    listSources:     ()       => call('list_sources'),
    getSourceSchema: (siteId) => call('get_source_schema', siteId),

    // Trial runs
    getTrialSteps:          ()              => call('get_trial_steps'),
    getDefaultTrialConfig:  ()              => call('get_default_trial_config'),
    getSampleRejectionEmail: ()             => call('get_sample_rejection_email'),
    triggerTrialRun:        (profileId, siteId, targetDate, trialConfig) =>
                                               call('trigger_trial_run', profileId, siteId, targetDate, trialConfig),
    resumeBooking:          (id, action)   => call('resume_booking', id, action),

    // Gmail / Settings
    getGmailStatus:  ()       => call('get_gmail_status'),
    startGmailOAuth: ()       => call('start_gmail_oauth'),
    revokeGmail:     ()       => call('revoke_gmail'),

    // V3 Flows
    listFlows:       ()                          => call('list_flows'),
    getFlow:         (flowId)                    => call('get_flow', flowId),
    runFlow:         (flowId, profileId, show)   => call('run_flow', flowId, profileId, show || false),
    validateFlow:    (flowId, profileId)         => call('validate_flow', flowId, profileId),
    cancelRun:       (runId)                     => call('cancel_run', runId),
    resumeRun:       (runId, action)             => call('resume_run', runId, action),

    // V3 Run History
    listRuns:        (flowId, limit)             => call('list_runs', flowId, limit),
    getRun:          (runId)                     => call('get_run', runId),
    getRunEvents:    (runId)                     => call('get_run_events', runId),
    getRunDecisions: (runId)                     => call('get_run_decisions', runId),
    getRunFailures:  (runId)                     => call('get_run_failures', runId),
    getFlowGraph:    (flowId)                    => call('get_flow_graph', flowId),
    getRunEventsSince: (runId, afterId)          => call('get_run_events_since', runId, afterId || 0),

    // V3 Contracts
    getActionContracts:  ()              => call('get_action_contracts'),
    getFlowViolations:   (flowId)        => call('get_flow_violations', flowId),

    // V3 Inspection
    getStepResult:       (runId, stepId) => call('get_step_result', runId, stepId),
    getScreenshot:       (path)          => call('get_screenshot', path),

    // V3 Palette + Block Library
    searchPalette:   ()               => call('search_palette'),
    listBlocks:      ()               => call('list_blocks'),
    saveBlock:       (data)           => call('save_block', data),

    // V3 Debug
    startDebugRun:   (flowId, profileId)          => call('start_debug_run', flowId, profileId),
    debugContinue:   (runId)                      => call('debug_continue', runId),
    debugSkip:       (runId)                      => call('debug_skip', runId),

    // V3 Schedules
    scheduleFlow:    (flowId, profileId, trigger) => call('schedule_flow', flowId, profileId, trigger),
    listSchedulesV3: ()                           => call('list_schedules_v3'),
    toggleScheduleV3: (id, enabled)              => call('toggle_schedule_v3', id, enabled),
    deleteScheduleV3: (id)                       => call('delete_schedule_v3', id),

    // V3 Process Planner
    startPlannerSession:     (flowId)                      => call('start_planner_session', flowId || null),
    getPlannerState:         (sessionId)                   => call('get_planner_state', sessionId),
    confirmPlannerIntent:    (sessionId, captureIndex, edits) =>
                               call('confirm_planner_intent', sessionId, captureIndex, edits || null),
    discardPlannerIntent:    (sessionId, captureIndex)     => call('discard_planner_intent', sessionId, captureIndex),
    addManualPlannerIntent:  (sessionId, intent)           => call('add_manual_planner_intent', sessionId, intent),
    capturePlannerScreenshot:(sessionId)                   => call('capture_planner_screenshot', sessionId),
    finishPlannerSession:    (sessionId, parameterized)    =>
                               call('finish_planner_session', sessionId, null, parameterized || null),
    cancelPlannerSession:    (sessionId)                   => call('cancel_planner_session', sessionId),
  };
})();
