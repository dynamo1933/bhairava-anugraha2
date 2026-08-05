/**
 * Bhairava Anugraha - Guest Telemetry & Analytics Tracker
 */
(function () {
  'use strict';

  // 1. Persistent Guest ID & Session ID
  function getGuestId() {
    let gid = localStorage.getItem('bhairava_guest_id');
    if (!gid) {
      gid = 'g_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now();
      localStorage.setItem('bhairava_guest_id', gid);
    }
    return gid;
  }

  function getSessionId() {
    let sid = sessionStorage.getItem('bhairava_session_id');
    if (!sid) {
      sid = 's_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now();
      sessionStorage.setItem('bhairava_session_id', sid);
    }
    return sid;
  }

  const guestId = getGuestId();
  const sessionId = getSessionId();
  const sessionStartTime = Date.now();
  let pageStartTime = Date.now();

  // 2. Browser & OS & Device Detection
  function detectClientInfo() {
    const ua = navigator.userAgent;
    let browser = 'Other';
    let os = 'Other';
    let device = 'Desktop';

    // Device
    if (/Tablet|iPad/i.test(ua) || (navigator.maxTouchPoints && navigator.maxTouchPoints > 2 && /Macintosh/i.test(ua))) {
      device = 'Tablet';
    } else if (/Mobi|Android|iPhone|iPod/i.test(ua)) {
      device = 'Mobile';
    }

    // OS
    if (/Win/i.test(ua)) os = 'Windows';
    else if (/Mac/i.test(ua) && !/iPhone|iPad/i.test(ua)) os = 'MacOS';
    else if (/Android/i.test(ua)) os = 'Android';
    else if (/iPhone|iPad|iPod/i.test(ua)) os = 'iOS';
    else if (/Linux/i.test(ua)) os = 'Linux';

    // Browser
    if (/Edg/i.test(ua)) browser = 'Edge';
    else if (/Chrome/i.test(ua) && !/Edg/i.test(ua)) browser = 'Chrome';
    else if (/Safari/i.test(ua) && !/Chrome/i.test(ua)) browser = 'Safari';
    else if (/Firefox/i.test(ua)) browser = 'Firefox';
    else if (/OPR|Opera/i.test(ua)) browser = 'Opera';

    return { browser, os, device };
  }

  const clientInfo = detectClientInfo();

  // Geo Location Cache
  let cachedGeo = { country: 'Unknown', city: 'Unknown' };
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    if (tz.includes('Asia/Kolkata') || tz.includes('India')) {
      cachedGeo.country = 'India';
    } else if (tz.includes('America/')) {
      cachedGeo.country = 'United States';
    } else if (tz.includes('Europe/')) {
      cachedGeo.country = 'Europe';
    }
  } catch (e) {}

  // Send Event Function
  function sendEvent(eventType, extraData = {}, useBeacon = false) {
    const pageDurationSec = Math.round((Date.now() - pageStartTime) / 1000);
    const sessionDurationSec = Math.round((Date.now() - sessionStartTime) / 1000);

    const payload = Object.assign({
      guest_id: guestId,
      session_id: sessionId,
      event_type: eventType,
      page_url: window.location.pathname + window.location.search,
      page_title: document.title || 'Bhairava Anugraha',
      browser: clientInfo.browser,
      os: clientInfo.os,
      device: clientInfo.device,
      country: cachedGeo.country,
      city: cachedGeo.city,
      page_duration_sec: pageDurationSec,
      session_duration_sec: sessionDurationSec,
      timestamp: new Date().toISOString()
    }, extraData);

    const blobData = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon('/api/analytics/collect', blobData);
    } else {
      fetch('/api/analytics/collect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true
      }).catch(function () {});
    }
  }

  // Initial Pageview
  sendEvent('pageview');

  // Heartbeat every 15 seconds to track active session & page duration
  setInterval(function () {
    sendEvent('heartbeat');
  }, 15000);

  // Page Unload Event
  window.addEventListener('beforeunload', function () {
    sendEvent('unload', {}, true);
  });

  // Global Tracking Utilities exposed to Window
  window.trackSearch = function (query) {
    if (!query) return;
    sendEvent('search', { search_query: String(query).trim() });
  };

  window.trackDownload = function (filename) {
    if (!filename) return;
    sendEvent('download', { download_file: String(filename).trim() });
  };

  window.trackApiCall = function (endpoint, responseTimeMs, statusCode = 200) {
    const errorFlag = statusCode >= 400 ? 1 : 0;
    sendEvent('api_call', {
      api_endpoint: endpoint,
      response_time_ms: responseTimeMs,
      status_code: statusCode,
      error_flag: errorFlag
    });
  };

  // Auto-track search inputs on page
  document.addEventListener('DOMContentLoaded', function () {
    const searchInputs = document.querySelectorAll('input[type="search"], #search-input, .search-box');
    searchInputs.forEach(function (input) {
      let timeout = null;
      input.addEventListener('input', function () {
        clearTimeout(timeout);
        const val = input.value.trim();
        if (val.length >= 3) {
          timeout = setTimeout(function () {
            window.trackSearch(val);
          }, 1000);
        }
      });
    });

    // Auto-track downloads on link clicks
    document.addEventListener('click', function (e) {
      const target = e.target.closest('a[download], a[href$=".pdf"], a[href$=".csv"], a[href$=".json"], a[href$=".db"]');
      if (target) {
        const file = target.getAttribute('download') || target.getAttribute('href');
        window.trackDownload(file);
      }
    });
  });
})();
