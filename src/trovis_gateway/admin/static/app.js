const defaults = {
  timing: { connect_timeout_s: 3, response_timeout_s: 2, total_request_timeout_s: 16, minimum_request_interval_s: .1, client_burst_idle_s: .2, connect_settle_delay_s: .25, reconnect_delay_s: 1, max_connection_age_s: 25 },
  retry: { read_retries: 2, write_retries: 0 },
  serial: { device: "", baudrate: 19200, data_bits: 8, parity: "N", stop_bits: 1 }
};
const communicationTimingFields = {
  connect_timeout_s: "connect-timeout",
  response_timeout_s: "response-timeout",
  total_request_timeout_s: "total-timeout",
  minimum_request_interval_s: "minimum-interval",
  connect_settle_delay_s: "settle-delay",
  reconnect_delay_s: "reconnect-delay",
  max_connection_age_s: "max-connection-age"
};
const schedulingWindows = {
  polling: defaults.timing.client_burst_idle_s,
  "trovis-view": .8
};
const schedulingDescriptions = {
  polling: "pollingHelp",
  "trovis-view": "trovisViewHelp",
  custom: "customHelp"
};
let config = { forwarding_enabled: true, active_profile_id: null, profiles: [] };
let selectedId = null;
let forwardingRequestInFlight = false;
let statusRequestId = 0;
const $ = id => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function showView(name) {
  document.querySelectorAll(".view").forEach(el => el.classList.toggle("hidden", el.id !== `${name}-view`));
  document.querySelectorAll(".nav-button").forEach(el => el.classList.toggle("active", el.dataset.view === name));
  if (name === "status") refreshStatus();
}

async function loadConfig(selectFirst = true) {
  config = await api("/api/config");
  renderProfiles();
  if (selectFirst && !selectedId && config.profiles.length) selectProfile(config.active_profile_id || config.profiles[0].id);
  if (selectFirst && !selectedId && !config.profiles.length) newProfile();
}

function renderProfiles() {
  const list = $("profile-list");
  $("empty-profiles").hidden = config.profiles.length > 0;
  list.innerHTML = "";
  config.profiles.forEach(profile => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `profile-item${profile.id === selectedId ? " selected" : ""}`;
    button.innerHTML = `<strong>${escapeHtml(profile.name)} ${profile.id === config.active_profile_id ? "<em>●</em>" : ""}</strong><span>${escapeHtml(target(profile))}</span>`;
    button.addEventListener("click", () => selectProfile(profile.id));
    list.append(button);
  });
}

function escapeHtml(value) { const div = document.createElement("div"); div.textContent = value ?? ""; return div.innerHTML; }
function target(profile) { return profile.transport === "serial_rtu" ? profile.serial.device : `${profile.host}:${profile.port}`; }
function number(id) { return Number($(id).value); }

function showSchedulingPreset(preset) {
  $("timing-preset").value = preset;
  showMessage("timing-preset-description", schedulingDescriptions[preset]);
}

function loadTiming(timing) {
  for (const [key, id] of Object.entries(communicationTimingFields)) {
    $(id).value = timing[key] ?? defaults.timing[key];
  }
  const windowSeconds = timing.client_burst_idle_s ?? .8;
  $("client-burst-idle").value = windowSeconds;
  const preset = Object.keys(schedulingWindows).find(name => schedulingWindows[name] === windowSeconds);
  showSchedulingPreset(preset ?? "custom");
}

function selectProfile(id) {
  selectedId = id;
  const profile = config.profiles.find(item => item.id === id);
  if (!profile) return newProfile();
  $("profile-id").value = profile.id;
  $("name").value = profile.name;
  $("description").value = profile.description;
  $("transport").value = profile.transport;
  $("host").value = profile.host;
  $("address-preference").value = profile.address_preference ?? "system";
  $("port").value = profile.port;
  $("upstream-unit-id").value = profile.upstream_unit_id;
  $("access-key").value = "";
  $("clear-key").checked = false;
  showMessage("key-state", profile.access_key_configured ? "keyConfigured" : "keyNotConfigured");
  $("serial-device").value = profile.serial.device;
  $("baudrate").value = profile.serial.baudrate;
  $("data-bits").value = profile.serial.data_bits;
  $("parity").value = profile.serial.parity;
  $("stop-bits").value = profile.serial.stop_bits;
  loadTiming(profile.timing);
  $("read-retries").value = profile.retry.read_retries;
  $("write-retries").value = profile.retry.write_retries;
  $("delete-profile").classList.remove("hidden");
  $("activate-profile").classList.toggle("hidden", profile.id === config.active_profile_id);
  transportChanged(); renderProfiles(); message("");
}

function newProfile() {
  selectedId = null;
  $("profile-form").reset();
  $("profile-id").value = ""; $("port").value = 502; $("upstream-unit-id").value = 247;
  $("transport").value = "rtu_over_tcp";
  $("baudrate").value = defaults.serial.baudrate; $("data-bits").value = 8; $("parity").value = "N"; $("stop-bits").value = 1;
  loadTiming(defaults.timing);
  $("read-retries").value = defaults.retry.read_retries; $("write-retries").value = defaults.retry.write_retries;
  showMessage("key-state", "keyNotConfigured");
  $("delete-profile").classList.add("hidden"); $("activate-profile").classList.add("hidden");
  transportChanged(); renderProfiles(); message(""); $("name").focus();
}

function payload() {
  return {
    name: $("name").value.trim(), description: $("description").value.trim(), transport: $("transport").value,
    host: $("host").value.trim(), port: number("port"), upstream_unit_id: number("upstream-unit-id"),
    address_preference: $("address-preference").value,
    access_key: $("access-key").value, clear_access_key: $("clear-key").checked, key_mode: "pass-through",
    serial: { device: $("serial-device").value.trim(), baudrate: number("baudrate"), data_bits: number("data-bits"), parity: $("parity").value, stop_bits: number("stop-bits") },
    timing: {
      ...Object.fromEntries(Object.entries(communicationTimingFields).map(([key, id]) => [key, number(id)])),
      client_burst_idle_s: number("client-burst-idle")
    },
    retry: { read_retries: number("read-retries"), write_retries: number("write-retries") }
  };
}

function transportChanged() {
  const serial = $("transport").value === "serial_rtu";
  $("serial-fields").classList.toggle("hidden", !serial); $("host-field").classList.toggle("hidden", serial); $("port-field").classList.toggle("hidden", serial);
  $("address-preference-field").classList.toggle("hidden", serial);
  $("host").required = !serial; $("serial-device").required = serial;
}

function message(render, error = false) {
  showText("form-message", render);
  $("form-message").classList.toggle("error", error);
}

async function saveProfile(event) {
  event.preventDefault(); message(() => t("saving"));
  try {
    const id = $("profile-id").value;
    const customWindow = $("timing-preset").value === "custom";
    const saved = await api(id ? `/api/profiles/${id}` : "/api/profiles", { method: id ? "PUT" : "POST", body: JSON.stringify(payload()) });
    selectedId = saved.id;
    await loadConfig(false);
    selectProfile(saved.id);
    if (customWindow) showSchedulingPreset("custom");
    message(() => t("saved"));
  } catch (error) { message(() => t("saveFailed", { detail: error.message }), true); }
}

async function testProfile() {
  message(() => t("testing"));
  try {
    const body = payload();
    if (selectedId) body.id = selectedId;
    const result = await api("/api/test-connection", { method: "POST", body: JSON.stringify(body) });
    message(() => connectionResultText(result), !result.ok);
  }
  catch (error) {
    message(() => error.message === "connection test timed out"
      ? t("testTimedOut")
      : t("testFailed", { detail: error.message }), true);
  }
}

function connectionResultText(result) {
  const timings = [t("testTotal", { ms: result.latency_ms })];
  if (result.dns_latency_ms != null) timings.push(`DNS ${result.dns_latency_ms} ms`);
  if (result.tcp_latency_ms != null) timings.push(`TCP ${result.tcp_latency_ms} ms`);
  let detail = result.detail;
  if (result.transport === "serial_rtu") detail = t(result.ok ? "serialPresent" : "serialMissing");
  if (result.ok && result.resolved_target) detail = t("tcpConnected", { target: result.resolved_target });
  return t("testResult", {
    status: t(result.ok ? "reachable" : "unreachable"),
    target: result.target,
    unit: result.upstream_unit_id,
    timings: timings.join(" · "),
    detail,
  });
}

async function activateProfile() { try { await api(`/api/profiles/${selectedId}/activate`, { method:"POST", body:"{}" }); await loadConfig(false); selectProfile(selectedId); message(() => t("profileActivated")); } catch(error) { message(() => t("activationFailed", { detail: error.message }), true); } }
async function deleteProfile() { if (!selectedId || !confirm(t("deletePrompt"))) return; try { await api(`/api/profiles/${selectedId}`, {method:"DELETE"}); selectedId=null; await loadConfig(); if (!config.profiles.length) newProfile(); message(() => t("profileDeleted")); } catch(error) { message(() => t("deleteFailed", { detail: error.message }), true); } }

async function refreshStatus() {
  const requestId = ++statusRequestId;
  try {
    const status = await api("/api/status"), metrics = status.metrics, active = status.active_profile;
    if (requestId !== statusRequestId) return;
    $("release-version").textContent = status.version;
    $("health-dot").classList.toggle("ok", status.forwarding_enabled);
    $("health-dot").classList.toggle("paused", !status.forwarding_enabled);
    showMessage("health-label", status.forwarding_enabled ? "proxyReady" : "forwardingPaused");
    if (!forwardingRequestInFlight) {
      $("forwarding-toggle").checked = status.forwarding_enabled;
      updateForwardingControls();
    }
    showMessage("proxy-badge", status.forwarding_enabled ? "ready" : "paused");
    $("proxy-badge").classList.toggle("status-indicator-ok", status.forwarding_enabled);
    $("proxy-badge").classList.toggle("status-indicator-paused", !status.forwarding_enabled);
    $("listener").textContent = `${status.listener.address}:${status.listener.port}`;
    $("requests").textContent = metrics.requests; $("clients").textContent = metrics.downstream_clients; $("queue").textContent = metrics.queue_depth; $("retries").textContent = metrics.retries; $("timeouts").textContent = metrics.timeouts; $("reconnects").textContent = metrics.reconnects;
    showText("active-profile-name", () => active ? active.name : t("noActiveProfile"));
    if (active) {
      showMessage("active-profile-target", "profileTarget", { target: target(active), unit: active.upstream_unit_id });
    } else {
      showMessage("active-profile-target", "createProfile");
    }
    showMessage("upstream-badge", metrics.upstream_connected ? "connected" : "disconnected");
    $("upstream-badge").classList.toggle("ok", metrics.upstream_connected);
  } catch (_) {
    if (requestId !== statusRequestId) return;
    $("health-dot").classList.remove("ok", "paused");
    showMessage("health-label", "unavailable");
  }
}

async function resetCounters() {
  const button = $("reset-counters");
  if (button.disabled || !confirm(t("resetPrompt"))) return;

  const message = $("reset-counters-message");
  button.disabled = true;
  showText(message.id, "");
  message.classList.remove("error");
  try {
    await api("/api/metrics/reset", { method: "POST", body: "{}" });
    await refreshStatus();
    showMessage(message.id, "countersReset");
  } catch (error) {
    showMessage(message.id, "resetFailed", { detail: error.message });
    message.classList.add("error");
  } finally {
    button.disabled = false;
  }
}

function updateForwardingControls() {
  const enabled = $("forwarding-toggle").checked;
  showMessage("forwarding-label", enabled ? "on" : "off");
}

async function saveForwardingState() {
  forwardingRequestInFlight = true;
  updateForwardingControls();
  showMessage("forwarding-message", "saving");
  $("forwarding-message").classList.remove("error");
  try {
    await api("/api/forwarding", { method: "POST", body: JSON.stringify({ enabled: $("forwarding-toggle").checked }) });
    const result = $("forwarding-toggle").checked ? "forwardingActive" : "forwardingPausedDetail";
    showMessage("forwarding-message", result);
  } catch (error) {
    showMessage("forwarding-message", "forwardingFailed", { detail: error.message });
    $("forwarding-message").classList.add("error");
  } finally {
    forwardingRequestInFlight = false;
    await refreshStatus();
  }
}

document.querySelectorAll(".nav-button").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
$("reset-counters").addEventListener("click", resetCounters);
$("new-profile").addEventListener("click", newProfile); $("profile-form").addEventListener("submit", saveProfile);
$("transport").addEventListener("change", transportChanged); $("test-profile").addEventListener("click", testProfile); $("activate-profile").addEventListener("click", activateProfile); $("delete-profile").addEventListener("click", deleteProfile);
$("forwarding-toggle").addEventListener("change", saveForwardingState);
$("timing-preset").addEventListener("change", event => {
  const preset = event.target.value;
  if (preset !== "custom") $("client-burst-idle").value = schedulingWindows[preset];
  showSchedulingPreset(preset);
});
$("client-burst-idle").addEventListener("input", () => showSchedulingPreset("custom"));
$("advanced-timing").addEventListener("invalid", () => { $("advanced-timing").open = true; }, true);
$("toggle-key").addEventListener("click", () => {
  const input = $("access-key");
  input.type = input.type === "text" ? "password" : "text";
  updateKeyToggle();
});
initializeLanguage();
loadConfig().catch(() => {}); refreshStatus(); setInterval(() => { if (!$("status-view").classList.contains("hidden")) refreshStatus(); }, 5000);
