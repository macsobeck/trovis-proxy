const defaults = {
  timing: { connect_timeout_s: 3, response_timeout_s: 2, total_request_timeout_s: 8, minimum_request_interval_s: .1, client_burst_idle_s: .25, connect_settle_delay_s: .25, reconnect_delay_s: 1, max_connection_age_s: 25 },
  retry: { read_retries: 2, write_retries: 0 },
  serial: { device: "", baudrate: 19200, data_bits: 8, parity: "N", stop_bits: 1 }
};
let config = { active_profile_id: null, profiles: [] };
let selectedId = null;
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
  if (!config.profiles.length) { list.innerHTML = '<div class="empty">No controller profiles yet.</div>'; return; }
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

function selectProfile(id) {
  selectedId = id;
  const profile = config.profiles.find(item => item.id === id);
  if (!profile) return newProfile();
  $("profile-id").value = profile.id;
  $("name").value = profile.name;
  $("description").value = profile.description;
  $("transport").value = profile.transport;
  $("host").value = profile.host;
  $("port").value = profile.port;
  $("upstream-unit-id").value = profile.upstream_unit_id;
  $("access-key").value = "";
  $("clear-key").checked = false;
  $("key-state").textContent = profile.access_key_configured ? "Access key configured" : "Not configured";
  $("serial-device").value = profile.serial.device;
  $("baudrate").value = profile.serial.baudrate;
  $("data-bits").value = profile.serial.data_bits;
  $("parity").value = profile.serial.parity;
  $("stop-bits").value = profile.serial.stop_bits;
  $("connect-timeout").value = profile.timing.connect_timeout_s;
  $("response-timeout").value = profile.timing.response_timeout_s;
  $("total-timeout").value = profile.timing.total_request_timeout_s;
  $("minimum-interval").value = profile.timing.minimum_request_interval_s;
  $("client-burst-idle").value = profile.timing.client_burst_idle_s ?? defaults.timing.client_burst_idle_s;
  $("settle-delay").value = profile.timing.connect_settle_delay_s;
  $("reconnect-delay").value = profile.timing.reconnect_delay_s;
  $("max-connection-age").value = profile.timing.max_connection_age_s ?? defaults.timing.max_connection_age_s;
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
  $("connect-timeout").value = defaults.timing.connect_timeout_s; $("response-timeout").value = defaults.timing.response_timeout_s; $("total-timeout").value = defaults.timing.total_request_timeout_s;
  $("minimum-interval").value = defaults.timing.minimum_request_interval_s; $("client-burst-idle").value = defaults.timing.client_burst_idle_s; $("settle-delay").value = defaults.timing.connect_settle_delay_s; $("reconnect-delay").value = defaults.timing.reconnect_delay_s; $("max-connection-age").value = defaults.timing.max_connection_age_s;
  $("read-retries").value = defaults.retry.read_retries; $("write-retries").value = defaults.retry.write_retries;
  $("key-state").textContent = "Not configured";
  $("delete-profile").classList.add("hidden"); $("activate-profile").classList.add("hidden");
  transportChanged(); renderProfiles(); message(""); $("name").focus();
}

function payload() {
  return {
    name: $("name").value.trim(), description: $("description").value.trim(), transport: $("transport").value,
    host: $("host").value.trim(), port: number("port"), upstream_unit_id: number("upstream-unit-id"),
    access_key: $("access-key").value, clear_access_key: $("clear-key").checked, key_mode: "pass-through",
    serial: { device: $("serial-device").value.trim(), baudrate: number("baudrate"), data_bits: number("data-bits"), parity: $("parity").value, stop_bits: number("stop-bits") },
    timing: { connect_timeout_s: number("connect-timeout"), response_timeout_s: number("response-timeout"), total_request_timeout_s: number("total-timeout"), minimum_request_interval_s: number("minimum-interval"), client_burst_idle_s: number("client-burst-idle"), connect_settle_delay_s: number("settle-delay"), reconnect_delay_s: number("reconnect-delay"), max_connection_age_s: number("max-connection-age") },
    retry: { read_retries: number("read-retries"), write_retries: number("write-retries") }
  };
}

function transportChanged() {
  const serial = $("transport").value === "serial_rtu";
  $("serial-fields").classList.toggle("hidden", !serial); $("host-field").classList.toggle("hidden", serial); $("port-field").classList.toggle("hidden", serial);
  $("host").required = !serial; $("serial-device").required = serial;
}

function message(text, error = false) { $("form-message").textContent = text; $("form-message").classList.toggle("error", error); }

async function saveProfile(event) {
  event.preventDefault(); message("Saving …");
  try {
    const id = $("profile-id").value;
    const saved = await api(id ? `/api/profiles/${id}` : "/api/profiles", { method: id ? "PUT" : "POST", body: JSON.stringify(payload()) });
    selectedId = saved.id; await loadConfig(false); selectProfile(saved.id); message("Profile saved.");
  } catch (error) { message(error.message, true); }
}

async function testProfile() {
  message("Testing connection …");
  try { const body = payload(); if (selectedId) body.id = selectedId; const result = await api("/api/test-connection", { method:"POST", body:JSON.stringify(body) }); message(`${result.ok ? "Reachable" : "Not reachable"}: ${result.target} · Unit ${result.upstream_unit_id} · ${result.latency_ms} ms · Modbus test not performed. ${result.detail}`, !result.ok); }
  catch (error) { message(error.message, true); }
}

async function activateProfile() { try { await api(`/api/profiles/${selectedId}/activate`, { method:"POST", body:"{}" }); await loadConfig(false); selectProfile(selectedId); message("Profile activated."); } catch(error) { message(error.message, true); } }
async function deleteProfile() { if (!selectedId || !confirm("Delete this connection profile?")) return; try { await api(`/api/profiles/${selectedId}`, {method:"DELETE"}); selectedId=null; await loadConfig(); if (!config.profiles.length) newProfile(); message("Profile deleted."); } catch(error) { message(error.message,true); } }

async function refreshStatus() {
  try {
    const status = await api("/api/status"), metrics = status.metrics, active = status.active_profile;
    $("release-version").textContent = `Release ${status.version}`;
    $("health-dot").classList.add("ok"); $("health-label").textContent = "Gateway ready";
    $("listener").textContent = `${status.listener.address}:${status.listener.port}`;
    $("requests").textContent = metrics.requests; $("clients").textContent = metrics.downstream_clients; $("queue").textContent = metrics.queue_depth; $("retries").textContent = metrics.retries; $("timeouts").textContent = metrics.timeouts; $("reconnects").textContent = metrics.reconnects;
    $("active-profile-name").textContent = active ? active.name : "No active profile"; $("active-profile-target").textContent = active ? `${target(active)} · Unit ${active.upstream_unit_id}` : "Create a profile under Controller connection.";
    $("upstream-badge").textContent = metrics.upstream_connected ? "Connected" : "Disconnected"; $("upstream-badge").classList.toggle("ok", metrics.upstream_connected);
  } catch (_) { $("health-dot").classList.remove("ok"); $("health-label").textContent = "Gateway unavailable"; }
}

document.querySelectorAll(".nav-button").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
$("refresh-status").addEventListener("click", refreshStatus); $("new-profile").addEventListener("click", newProfile); $("profile-form").addEventListener("submit", saveProfile);
$("transport").addEventListener("change", transportChanged); $("test-profile").addEventListener("click", testProfile); $("activate-profile").addEventListener("click", activateProfile); $("delete-profile").addEventListener("click", deleteProfile);
$("toggle-key").addEventListener("click", () => { const input=$("access-key"), visible=input.type === "text"; input.type=visible?"password":"text"; $("toggle-key").textContent=visible?"Show":"Hide"; });
loadConfig().catch(() => {}); refreshStatus(); setInterval(() => { if (!$("status-view").classList.contains("hidden")) refreshStatus(); }, 5000);
