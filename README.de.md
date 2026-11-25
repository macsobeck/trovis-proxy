# TROVIS Modbus Proxy für den Zugriff von Smart-Home-Anwendungen auf SAMSON-Regler

[English](README.md) | Deutsch

Der TROVIS Modbus Proxy ist ein selbst gehosteter Modbus-Proxy. Er verbindet Smart-Home-Anwendungen
wie SAMSON TROVIS-VIEW, Home Assistant und Node-RED zuverlässig mit TROVIS-Heizungsreglern,
darunter Modelle der Baureihe SAMSON TROVIS 5573-1xxx. Er stellt den Anwendungen einen stabilen
Modbus-TCP-Endpunkt bereit und verbindet sich über Modbus TCP, RTU-over-TCP oder Serial RTU
mit dem Regler.

> **Neu in 1.2.3**
>
> - **Zweisprachige Oberfläche.** Englisch ist die Standardsprache. Die Kopfzeile bietet einen
>   Wechsel zu Deutsch. Der Browser merkt sich die Auswahl.
> - **Einfachere Client-Steuerung.** Wählen Sie Mehrclientbetrieb mit oder ohne TROVIS-VIEW
>   oder ein eigenes Sequenzfenster. Die erweiterten Timing-Werte für den Regler stehen separat.
>
> Einzelheiten stehen im [Changelog](CHANGELOG.md#123---2026-11-25).

```text
Client-Anwendung → Modbus TCP → TROVIS Modbus Proxy → Modbus TCP / RTU-over-TCP / Serial RTU → Regler
```

Der Modbus Proxy leitet Modbus-PDUs unverändert weiter und verwendet keine regler- oder
firmwarespezifische Adressübersetzung. Der Code für TROVIS 5573-1 FW 3.09 in
`src/trovis_manager/` bleibt eine getrennte, schreibgeschützte Integrations- und
Forschungsumgebung; er ist nicht Bestandteil des Modbus-Proxy-Kerns.

## Hauptvorteile

- Stabiler Modbus-TCP-Zugriff für TROVIS-VIEW, Home Assistant, Node-RED und weitere Clients auf Port `7112`.
- Stabile Firmware-Updates des Reglers über TROVIS-VIEW mit derselben zuverlässigen
  Proxy-Verbindung.
- Reglerverbindungen über Modbus TCP, transparentes RTU-over-TCP oder Serial RTU.
- Docker-Compose-Bereitstellung für Linux-Server und NAS-Systeme wie z.B. Synology.
- Dauerhaft gespeicherte Reglerprofile mit einer responsiven browserbasierten
  Administrationsoberfläche.
- Koordinierung mehrerer Clients, sichere Wiederholungen von Lesezugriffen, geschützte
  Schreibvorgänge, zeitliche Steuerung und proaktive Neuverbindungen.
- Transparenter Betrieb mit seriellen USR-Ethernet-Adaptern im Protokollmodus `None`.
- Reglerneutraler Modbus-Proxy-Kern ohne fest hinterlegte Registertabellen oder synthetische Werte.

## Sicherheitshinweis – OpenSSL-Befunde

Docker Scout meldet derzeit sechs Befunde, die aus dem OpenSSL-3.5.7-Laufzeitpaket von Debian 13
stammen. Sie haben ihren Ursprung nicht im Quellcode des TROVIS Modbus Proxy.

Der Proxy verwendet unverschlüsseltes Modbus TCP und serielle Kommunikation. Die betroffenen
Funktionen für QUIC, AES-GCM-SIV, CMS-Verschlüsselung und spezielle PEM-Stack-Verarbeitung werden
nicht direkt verwendet. Die aktuelle Gefährdung erscheint deshalb begrenzt. Die Befunde bleiben
dennoch sichtbar, bis korrigierte Pakete verfügbar sind.

OpenSSL hat korrigierte Upstream-Versionen für den **1. Dezember 2026** angekündigt. Sobald auch
ein entsprechend korrigiertes Debian-Paket verfügbar ist, wird das Container-Image neu erstellt,
für AMD64 und ARM64 getestet, erneut geprüft und als Wartungsversion veröffentlicht.

Durch diesen Hinweis wird keine Schwachstelle unterdrückt oder als behoben gekennzeichnet.

Weitere Informationen:

- https://openssl-library.org/news/secadv/20261110.txt
- https://openssl-library.org/news/secadv/20261117.txt

## Warum dieser Modbus Proxy?

Ich verwende TROVIS-VIEW mit dem Modbus-Protokoll, um die Konfiguration meines Heizungsreglers
SAMSON TROVIS 5573-1xxx zu verwalten. Der `ModbusTCP`-Modus meines Modbus-Adapters
USR-TCP232-E2 stellte jedoch keine zuverlässige Verbindung bereit. Die Kommunikation war instabil,
wodurch Lese- und Schreibvorgänge fehlschlugen. Ähnliche Probleme können auch mit anderen
seriellen Ethernet-Adaptern auftreten, die selbst eine Modbus-TCP-zu-RTU-Konvertierung ausführen.

Die zuverlässige Konfiguration besteht darin, den USR-Adapter als `TCP Server` mit dem
Protokollmodus `None` einzurichten und anschließend im Reglerprofil des Modbus Proxy
`RTU-over-TCP` auszuwählen. Dadurch bleibt der Adapter transparent, während der Modbus Proxy die
Modbus-TCP-zu-RTU-Rahmung übernimmt.

Dieses Interoperabilitätsproblem war der ursprüngliche Anlass für die Entwicklung des TROVIS
Modbus Proxy. Inzwischen hat sich das Projekt zu einer allgemeineren Kommunikationsschicht mit
weiteren Stärken entwickelt:

- **Koordinierter Mehr-Client-Zugriff:** TROVIS-VIEW, Home Assistant, Node-RED, TROVIS 55 Pro und weitere
  Modbus-TCP-Clients können über einen Modbus Proxy auf denselben Regler zugreifen. Die
  Anfragesequenzen eines Clients werden in eine Warteschlange gestellt und zusammengehalten,
  damit konkurrierende Anwendungen keine fehlerhaften Reglerauslesungen verursachen.
- **Stabile Firmware-Updates:** Wenn der Adapter im transparenten Modus `None` arbeitet und der
  Modbus Proxy `RTU-over-TCP` verwendet, transportiert der Adapter die seriellen Modbus-RTU-Rahmen,
  ohne sie zu decodieren oder umzuschreiben. Die Nutzdaten der Modbus-PDUs bleiben unverändert.
  Dadurch entfällt die Protokollkonvertierung im Adapter und TROVIS-VIEW erhält einen stabilen
  Übertragungsweg für Firmware-Updates.
- **Transparente Protokollverarbeitung:** Modbus-Funktionscodes, Adressen und Werte werden
  unverändert weitergeleitet. Der Modbus Proxy ist weder von einer reglerspezifischen
  Registertabelle noch von einer synthetischen Adressübersetzung abhängig.
- **Flexible Reglerverbindungen:** Für die Verbindung zum Regler stehen Modbus TCP, transparentes
  RTU-over-TCP und Serial RTU zur Verfügung.
- **Zuverlässiges Verbindungsmanagement:** Einstellbare Anfrageabstände, Zeitüberschreitungen,
  sichere Wiederholungen von Lesezugriffen und proaktive Neuverbindungen stabilisieren die
  Kommunikation mit Reglern und Ethernet-Adaptern.
- **Kontrollierte Wartungspausen:** Die Weiterleitung kann angehalten werden, ohne den Dienst zu
  stoppen. Neue und bereits wartende Anfragen werden mit der Modbus-Ausnahme `0x0B` abgewiesen;
  aktive Anfragen werden sicher beendet und nichts wird zur späteren Ausführung gespeichert.
- **Client-Sequenzfenster:** Wählen Sie **Multi-client incl. TROVIS-VIEW**,
  **Multi-client without TROVIS-VIEW** oder **Custom**. Das Timing für Regler und Adapter steht
  unter **Advanced communication settings**. Details stehen in der
  [Timing-Konfiguration](docs/gateway/configuration.md#timing-presets).
- **Geschützte Schreibvorgänge:** Schreibvorgänge werden nach einem uneindeutigen Ergebnis niemals
  wiederholt. Dadurch sinkt das Risiko unbeabsichtigter Konfigurationsänderungen.
- **Einfacher selbst gehosteter Betrieb:** Docker Compose, dauerhafte Konfiguration und eine
  browserbasierte Administrationsoberfläche machen den Modbus Proxy für NAS-Systeme und andere
  dauerhaft laufende Linux-Rechner geeignet.
- **Betriebstransparenz:** Die Statusoberfläche zeigt den aktuellen Verbindungs- und Warteschlangenstatus
  sowie rücksetzbare Zähler für Anfragen, Wiederholungen, Zeitüberschreitungen und Neuverbindungen.

### Status des Modbus Proxy

![Statusübersicht des TROVIS Modbus Proxy für Modbus-TCP-Clients und einen SAMSON-Regler](docs/images/gateway-status.png)

*Statusübersicht mit Weiterleitungssteuerung, rücksetzbaren Zählern und Sprachauswahl.*

### Reglerverbindung

![Reglerprofil des TROVIS Modbus Proxy mit Timing-Voreinstellung und Client-Sequenzfenster](docs/images/controller-connection.png)

*Client-Steuerung mit der Voreinstellung für mehrere Clients ohne TROVIS-VIEW und den erweiterten Kommunikationseinstellungen.*

*Beide Screenshots verwenden ein Beispielprofil und einen Beispiel-Hostnamen.*

![USR-Adapter für transparenten RTU-over-TCP-Betrieb](docs/images/usr-adapter-settings.png)

*Beispiel für den USR-Adapter: Socket A verwendet `TCP Server`, Protokollmodus `None` und den
lokalen Port `7112`.*

## Schnellstart mit Docker oder Python

### Docker Compose mit dem neuesten Docker-Hub-Image (empfohlen)

Das öffentliche Multi-Plattform-Image unterstützt Linux AMD64 und ARM64. Docker wählt automatisch
das passende Image aus.

```bash
mkdir -p data
sudo chown -R 1000:1000 data
docker compose pull
docker compose up -d
```

Öffnen Sie `http://localhost:8083/`. Die Standarddatei `compose.yaml` lädt
`docker.io/macsobeck/trovis-proxy:latest`; sie erstellt das `Dockerfile` des Repositorys nicht neu
und benötigt keine Anmeldung bei einer Registry. Der Container läuft mit UID/GID `1000:1000` und
veröffentlicht den TROVIS-VIEW-Listener auf Port `7112`.

### Native Python-Installation

Python 3.12 oder neuer wird benötigt.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,serial]'
mkdir -p data
trovis-gateway --listen-host 0.0.0.0 --listen-port 7112 \
  --admin-host 127.0.0.1 --admin-port 8080 \
  --config-path ./data/config.json
```

Öffnen Sie bei einer nativen Installation `http://127.0.0.1:8080/`.

Erstellen Sie ein Reglerprofil, testen Sie dessen Transportverbindung und aktivieren Sie es. Der
Verbindungstest öffnet ausschließlich den konfigurierten Transport und sendet keine erfundene
Modbus-Registeranfrage. Listener-Adresse und -Port sind Infrastruktureinstellungen aus
Umgebungsvariablen oder CLI-Argumenten und keine Felder des Reglerprofils.

Profildaten bleiben im Host-Verzeichnis `./data` gespeichert und erscheinen im Docker-Container
als `/data/config.json` mit dem Modus `0600`. Ein gespeicherter Zugriffsschlüssel wird in API und
Oberfläche maskiert. Er wird weder protokolliert noch als Metrik ausgegeben oder in den
Protokollverkehr eingefügt.

## Installationsanleitungen

Wählen Sie die [deutsche Schritt-für-Schritt-Anleitung](docs/gateway/installation.de.md) oder die
[englische Installationsanleitung](docs/gateway/installation.md). Sie behandeln:

- Voraussetzungen für Docker und Docker Compose;
- Installation auf einem Synology NAS, Bind-Mounts, UID/GID-Rechte und dauerhafte Speicherung;
- Reglerprofile für Modbus TCP, RTU-over-TCP und Serial RTU;
- Einstellungen für serielle USR-Ethernet-Adapter;
- TROVIS-VIEW-Netzwerkkonfiguration;
- Updates, Sicherungen, Diagnose und Fehlerbehebung.

## Sicherheitsmodell

- Nachgelagerte Unit IDs werden gespeichert und in Antworten wiederhergestellt; auf der
  Reglerseite wird die Unit ID des aktiven Profils verwendet.
- Lesezugriffe mit FC01–04 dürfen nach einem eindeutigen Transportfehler wiederholt werden.
- Schreibzugriffe mit FC05/06/0F/10 werden nach einem uneindeutigen Ergebnis niemals wiederholt.
- Unbekannte und herstellerspezifische Funktionscodes werden undurchsichtig weitergeleitet und
  bleiben nachvollziehbar.
- Alle Modbus-PDUs, einschließlich FC01-Adressen, werden unverändert weitergeleitet.
- Die geplante Erneuerung der TCP-Verbindung wird standardmäßig nach 25 Sekunden fällig und
  erfolgt vor der nächsten Abfragesequenz.
- Alle Anfragen an einen Regler werden serialisiert und zeitlich gesteuert. Aufeinanderfolgende
  Anfragen eines verbundenen Clients behalten kurzzeitig Vorrang, damit kein anderer Client eine
  Abfragesequenz unterbrechen kann.

Weitere Informationen finden Sie in der englischen Dokumentation zu
[Modbus-Proxy-Architektur](docs/gateway/architecture.md),
[Konfiguration](docs/gateway/configuration.md) und
[Protokollsicherheit](docs/gateway/protocol-safety.md). Release-Änderungen sind im
[Changelog](CHANGELOG.md) dokumentiert.

## Häufig gestellte Fragen

### Welche Anwendungen kann ich mit dem Proxy verbinden?

TROVIS-VIEW, Home Assistant, Node-RED, TROVIS 55 Pro und weitere Anwendungen können über
**Modbus TCP** auf den Proxy zugreifen, sofern sie diesen Verbindungsmodus unterstützen.

### Wie verbinde ich eine Anwendung mit dem Proxy?

Wählen Sie in der Anwendung **Modbus TCP** und geben Sie die IP-Adresse oder den DNS-Namen des
Proxy-Hosts sowie den Port **`7112`** ein. Den Transport vom Proxy zum Regler legen Sie separat
im Reglerprofil fest.

### Können mehrere Anwendungen gleichzeitig auf denselben Regler zugreifen?

Ja. Der Proxy arbeitet die Anfragen an den Regler nacheinander ab. Er hält zusammengehörige
Abfragen eines Clients innerhalb eines einstellbaren Zeitfensters zusammen. Während TROVIS-VIEW
eine Konfiguration ausliest, können Abfragen von Home Assistant oder Node-RED deshalb kurz warten.

### Welche Heizungsregler werden unterstützt?

Der dokumentierte Aufbau wurde mit einem **SAMSON TROVIS 5573-1xxx** getestet. Auch andere Regler
kommen infrage, wenn die Kommunikation über **Modbus TCP**, **RTU-over-TCP** oder **Serial RTU**
möglich ist.

### Wie richte ich einen seriellen USR-Ethernet-Adapter ein?

Stellen Sie Socket A des Adapters auf **`TCP Server`** und den Protokollmodus auf **`None`**.
Wählen Sie im Reglerprofil des Proxys **`RTU-over-TCP`**. Ihre Anwendungen verbinden sich per
**Modbus TCP** mit dem Proxy.

### Kann ich den Proxy auf einem NAS (z.B. von Synology) betreiben?

Ja. Auf einem NAS (z.B. von Synology) mit einem Container Manager können Sie den Proxy per Docker
Compose betreiben. Die Reglerprofile werden im eingebundenen Datenverzeichnis gespeichert und stehen
auch nach einem Container-Update zur Verfügung.

### Warum kann das zweite Auslesen in TROVIS-VIEW fehlschlagen?

Im getesteten Aufbau funktioniert das erste Auslesen nach einem Neustart von TROVIS-VIEW
zuverlässig. Beim zweiten Auslesen verwendet TROVIS-VIEW eine andere Abfolge von Abfragen. Dabei
kann eine Fehlermeldung auftreten. Das Verhalten zeigt sich auch bei direkter Verbindung zum
USR-Adapter und ist damit unabhängig vom Proxy. Ein Neustart von TROVIS-VIEW ermöglicht einen
weiteren Auslesevorgang.

## Entwicklungsunterstützung

Dieses Repository wird von macsobeck mit Unterstützung von OpenAI Codex für Codeanalyse,
Implementierung, Tests, Dokumentation und Release-Vorbereitung entwickelt und gepflegt. Alle
Änderungen werden vom Repository-Betreiber geprüft und veröffentlicht.

## Entwicklung

```bash
pytest
ruff check .
git diff --check
```

Die Standardtests verwenden ausschließlich lokale simulierte Server und benötigen keine echte
Hardware. Die bisherige Forschungs-CLI bleibt als `trovisctl` verfügbar; ihr Hardware-Ablauf ist
weiterhin schreibgeschützt. Lesen Sie vor einer Verbindung mit einem Regler die englische
Dokumentation zur [Hardwarevalidierung](docs/hardware-validation.md).

## Repository-Struktur

- `src/trovis_gateway/`: allgemeiner Modbus Proxy, Transporte, Konfiguration, API und
  Administrationsoberfläche.
- `src/trovis_manager/`: gerätespezifische schreibgeschützte Integrationsumgebung.
- `tests/gateway/`, `tests/unit/`, `tests/integration/`: automatisierte Testabdeckung.
- `reference/`: unveränderliche Quellartefakte und abgeleitete Forschungsdaten für FW 3.09.
- `docs/`: Architektur, Sicherheitsnachweise und Forschungsergebnisse.
