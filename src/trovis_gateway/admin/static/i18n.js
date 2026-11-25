const germanLabels = {
  "status": "Status",
  "controllerConnection": "Reglerverbindung",
  "loading": "Wird geladen",
  "overview": "Betriebsübersicht",
  "proxyStatus": "Modbus-Proxy-Status",
  "resetCounters": "Zähler zurücksetzen",
  "operation": "Betrieb",
  "forwardingControl": "Weiterleitung",
  "forwardingHelp": "Pausiere die Weiterleitung zum Regler. Laufende Anfragen werden abgeschlossen. Neue und wartende Anfragen erhalten den Modbus-Ausnahmecode 0x0B.",
  "on": "Ein",
  "downstream": "Client-Seite",
  "ready": "Bereit",
  "listener": "TROVIS-VIEW-Listener",
  "activeClients": "Aktive Clients",
  "requests": "Anfragen",
  "queue": "Warteschlange",
  "upstream": "Reglerseite",
  "disconnected": "Nicht verbunden",
  "activeProfile": "Aktives Profil",
  "noActiveProfile": "Kein aktives Profil",
  "target": "Ziel",
  "createProfile": "Lege ein Profil an.",
  "retries": "Wiederholungen",
  "timeouts": "Zeitüberschreitungen",
  "reconnects": "Neuverbindungen",
  "safety": "Sicherheitsgrenze",
  "safetyHelp": "Der Modbus Proxy leitet Modbus-PDUs transparent weiter. Gespeicherte Zugriffsschlüssel werden im Pass-through-Modus nicht in Nachrichten eingefügt.",
  "connectionDirection": "Modbus Proxy → Regler",
  "controllerConnectionHelp": "Verbindungsart, Ziel und Timing für den Regler einstellen.",
  "newProfile": "Neues Profil",
  "general": "Allgemein",
  "profile": "Profil",
  "profileHelp": "Name und optionale Beschreibung der Reglerverbindung.",
  "description": "Beschreibung",
  "connectionPath": "Verbindungsweg",
  "transportAndTarget": "Verbindungsart und Ziel",
  "transportHelp": "Einstellungen für die Verbindung vom Modbus Proxy zum Regler.",
  "transport": "Verbindungsart",
  "serialRtu": "Serielles RTU",
  "ipPreference": "Bevorzugte IP-Adressfamilie",
  "systemOrder": "Systemreihenfolge (Standard)",
  "preferIpv4": "IPv4 bevorzugen",
  "preferIpv6": "IPv6 bevorzugen",
  "ipPreferenceHelp": "Für DNS-Namen. Ist die erste Adressfamilie nicht erreichbar, kann der Proxy die andere versuchen.",
  "modbusUnit": "Modbus-Stationsadresse",
  "serialInterface": "Serielle Schnittstelle",
  "device": "Gerät",
  "baudRate": "Baudrate",
  "dataBits": "Datenbits",
  "parity": "Parität",
  "noParity": "Keine",
  "even": "Gerade",
  "odd": "Ungerade",
  "stopBits": "Stoppbits",
  "authorization": "Berechtigung",
  "access": "Zugriff",
  "accessHelp": "Die Oberfläche zeigt den Schlüssel verdeckt an. Der Proxy fügt ihn nicht in den Datenverkehr ein.",
  "accessKey": "Zugriffsschlüssel",
  "notConfigured": "Nicht konfiguriert",
  "removeKey": "Schlüssel entfernen",
  "removeKeyHelp": "Gespeicherten Schlüssel beim Speichern entfernen",
  "keyMode": "Schlüsselmodus",
  "keyModeHelp": "Bis zur Bestätigung des Protokollverhaltens bleibt das Einfügen des Schlüssels deaktiviert.",
  "timingConfiguration": "Timing-Konfiguration",
  "clientScheduling": "Client-Steuerung",
  "clientSchedulingHelp": "Lege fest, wie lange aufeinanderfolgende Anfragen eines Clients zusammenbleiben.",
  "schedulingPreset": "Voreinstellung",
  "withTrovisView": "Mehrere Clients mit TROVIS-VIEW",
  "withoutTrovisView": "Mehrere Clients ohne TROVIS-VIEW",
  "custom": "Benutzerdefiniert",
  "pollingHelp": "Für zyklische Abfragen etwa aus Home Assistant und Node-RED.",
  "clientWindow": "Client-Sequenzfenster",
  "clientWindowHelp": "Gib das Fenster in Sekunden an. Bei 0 wechseln sich wartende Clients nach jeder Anfrage ab.",
  "advancedSettings": "Erweiterte Kommunikationseinstellungen",
  "connectionTimeout": "Verbindungs-Timeout",
  "responseTimeout": "Antwort-Timeout",
  "totalTimeout": "Gesamt-Timeout",
  "totalTimeoutHelp": "Umfasst die Wartezeit in der Warteschlange, die Reglerkommunikation und Wiederholungen.",
  "minimumInterval": "Mindestabstand zwischen Anfragen",
  "postConnect": "Wartezeit nach Verbindungsaufbau",
  "preReconnect": "Wartezeit vor Neuverbindung",
  "maximumAge": "Maximales TCP-Verbindungsalter",
  "maximumAgeHelp": "Nach Ablauf dieser Zeit erneuert der Proxy die Verbindung vor der nächsten Client-Sequenz. 0 deaktiviert die geplante Neuverbindung.",
  "errorHandling": "Fehlerbehandlung",
  "retriesHelp": "Anzahl der zulässigen Wiederholungsversuche.",
  "readRequests": "Leseanfragen",
  "writeRequests": "Schreibanfragen",
  "writeRetryHelp": "Nur bei Anfragen, die nachweislich noch nicht gesendet wurden.",
  "deleteProfile": "Löschen",
  "testConnection": "Verbindung testen",
  "activateProfile": "Aktivieren",
  "save": "Speichern",
  "emptyProfiles": "Noch keine Reglerprofile vorhanden.",
  "releaseLabel": "Version",
  "homeLabel": "Startseite des Modbus Proxy",
  "navLabel": "Hauptnavigation",
  "languageLabel": "Sprache der Oberfläche",
  "connectionProfiles": "Verbindungsprofile",
  "namePlaceholder": "z. B. Heizungsanlage West",
  "descriptionPlaceholder": "Ort oder Zweck",
  "leaveKeyUnchanged": "Unverändert lassen"
};

const messages = {
  pollingHelp: ["For polling clients such as Home Assistant and Node-RED.", "Für zyklische Abfragen etwa aus Home Assistant und Node-RED."],
  trovisViewHelp: ["Keeps TROVIS-VIEW readouts together while other clients poll.", "Hält TROVIS-VIEW-Auslesevorgänge zusammen, während andere Clients abfragen."],
  customHelp: ["Enter your own sequence window below.", "Gib unten ein eigenes Sequenzfenster ein."],
  keyConfigured: ["Access key configured", "Zugriffsschlüssel konfiguriert"],
  keyNotConfigured: ["Not configured", "Nicht konfiguriert"],
  showKey: ["Show", "Anzeigen"],
  hideKey: ["Hide", "Ausblenden"],
  showKeyLabel: ["Show access key", "Zugriffsschlüssel anzeigen"],
  hideKeyLabel: ["Hide access key", "Zugriffsschlüssel ausblenden"],
  saving: ["Saving …", "Wird gespeichert …"],
  saved: ["Profile saved.", "Profil gespeichert."],
  saveFailed: ["Could not save the profile. {detail}", "Das Profil konnte nicht gespeichert werden. {detail}"],
  testing: ["Testing connection …", "Verbindung wird getestet …"],
  testFailed: ["Connection test failed. {detail}", "Verbindungstest fehlgeschlagen. {detail}"],
  testTimedOut: ["Connection test timed out.", "Zeitüberschreitung beim Verbindungstest."],
  testTotal: ["{ms} ms total", "{ms} ms insgesamt"],
  testResult: [
    "{status}: {target} · Unit {unit} · {timings}. {detail}",
    "{status}: {target} · Station {unit} · {timings}. {detail}",
  ],
  reachable: ["Reachable", "Erreichbar"],
  unreachable: ["Not reachable", "Nicht erreichbar"],
  serialPresent: [
    "Serial device exists. The test sent no protocol request.",
    "Das serielle Gerät ist vorhanden. Der Test hat keine Protokollanfrage gesendet.",
  ],
  serialMissing: ["Serial device does not exist.", "Das serielle Gerät ist nicht vorhanden."],
  tcpConnected: [
    "TCP connection established via {target}. The test sent no Modbus request.",
    "TCP-Verbindung über {target} hergestellt. Der Test hat keine Modbus-Anfrage gesendet.",
  ],
  profileActivated: ["Profile activated.", "Profil aktiviert."],
  activationFailed: ["Could not activate the profile. {detail}", "Das Profil konnte nicht aktiviert werden. {detail}"],
  deletePrompt: ["Delete this connection profile?", "Dieses Verbindungsprofil löschen?"],
  profileDeleted: ["Profile deleted.", "Profil gelöscht."],
  deleteFailed: ["Could not delete the profile. {detail}", "Das Profil konnte nicht gelöscht werden. {detail}"],
  proxyReady: ["Modbus Proxy ready", "Modbus Proxy bereit"],
  forwardingPaused: ["Forwarding paused", "Weiterleitung pausiert"],
  ready: ["Ready", "Bereit"],
  paused: ["Paused", "Pausiert"],
  noActiveProfile: ["No active profile", "Kein aktives Profil"],
  profileTarget: ["{target} · Unit {unit}", "{target} · Station {unit}"],
  createProfile: [
    "Create a profile under Controller connection.",
    "Lege unter Reglerverbindung ein Profil an.",
  ],
  connected: ["Connected", "Verbunden"],
  disconnected: ["Disconnected", "Nicht verbunden"],
  unavailable: ["Modbus Proxy unavailable", "Modbus Proxy nicht erreichbar"],
  resetPrompt: [
    "Reset requests, retries, timeouts, and reconnects to zero?",
    "Die Zähler für Anfragen, Wiederholungen, Zeitüberschreitungen und Neuverbindungen auf null setzen?",
  ],
  countersReset: ["Counters reset.", "Zähler zurückgesetzt."],
  resetFailed: ["Could not reset the counters. {detail}", "Die Zähler konnten nicht zurückgesetzt werden. {detail}"],
  on: ["On", "Ein"],
  off: ["Off", "Aus"],
  forwardingActive: ["Forwarding is active.", "Die Weiterleitung ist aktiv."],
  forwardingPausedDetail: [
    "Forwarding is paused. The proxy rejects new requests.",
    "Die Weiterleitung ist pausiert. Der Proxy weist neue Anfragen ab.",
  ],
  forwardingFailed: [
    "Could not change forwarding. {detail}",
    "Die Weiterleitung konnte nicht umgeschaltet werden. {detail}",
  ],
};

const localeStorageKey = "trovis-proxy-language";
const localizedContent = [...document.querySelectorAll("[data-i18n]")].map(element => ({
  element,
  attribute: element.dataset.i18nAttr,
  english: element.dataset.i18nAttr ? element.getAttribute(element.dataset.i18nAttr) : element.textContent,
  german: germanLabels[element.dataset.i18n],
}));
const localizedText = new Map();
let uiLanguage = "en";

function t(key, values = {}) {
  const template = messages[key][uiLanguage === "de" ? 1 : 0];
  return template.replace(/\{(\w+)\}/g, (_, name) => values[name]);
}

function showText(id, render) {
  const element = document.getElementById(id);
  if (typeof render === "function") {
    localizedText.set(element, render);
    element.textContent = render();
  } else {
    localizedText.delete(element);
    element.textContent = render;
  }
}

function showMessage(id, key, values) {
  showText(id, () => t(key, values));
}

function applyLanguage(language) {
  uiLanguage = language === "de" ? "de" : "en";
  document.documentElement.lang = uiLanguage;
  document.getElementById("ui-language").value = uiLanguage;
  for (const { element, attribute, english, german } of localizedContent) {
    const text = uiLanguage === "de" ? german : english;
    if (attribute) element.setAttribute(attribute, text);
    else element.textContent = text;
  }
  for (const [element, render] of localizedText) element.textContent = render();
  updateKeyToggle();
}

function updateKeyToggle() {
  const visible = document.getElementById("access-key").type === "text";
  const button = document.getElementById("toggle-key");
  button.textContent = t(visible ? "hideKey" : "showKey");
  button.setAttribute("aria-label", t(visible ? "hideKeyLabel" : "showKeyLabel"));
}

function initializeLanguage() {
  let saved = null;
  try { saved = localStorage.getItem(localeStorageKey); } catch (_) { /* Browser storage can be unavailable. */ }
  applyLanguage(saved);
  document.getElementById("ui-language").addEventListener("change", event => {
    applyLanguage(event.target.value);
    try { localStorage.setItem(localeStorageKey, uiLanguage); } catch (_) { /* The tab still uses the chosen language. */ }
  });
}
