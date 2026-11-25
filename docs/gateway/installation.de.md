# Installationsanleitung

[English](installation.md) | Deutsch

Diese Anleitung zeigt, wie Sie den TROVIS Modbus Proxy installieren und Client-Anwendungen wie
TROVIS-VIEW, Home Assistant und Node-RED mit einem SAMSON-TROVIS-Regler verbinden.

```text
Client-Anwendung → Modbus TCP → Modbus Proxy → ausgewählter Transport → Regler
```

Docker Compose ist die empfohlene Installationsmethode. Eine native Python-Installation für die
Entwicklung oder den direkten Zugriff auf eine serielle Schnittstelle wird am Ende beschrieben.

## 1. Voraussetzungen prüfen

Sie benötigen:

- einen Linux-, macOS- oder Windows-Rechner mit Netzwerkzugriff auf den Regler;
- Docker Engine mit Compose-Plugin oder Docker Desktop;
- TCP-Port `7112` des Docker-Hosts, erreichbar von den Client-Anwendungen;
- Host, Port, Modbus-Stationsadresse und Transportart des Reglers;
- Python 3.12 oder neuer nur für die native Installation.

Docker prüfen:

```bash
docker --version
docker compose version
```

Die mitgelieferte Compose-Konfiguration veröffentlicht die Administrationsoberfläche auf Host-Port
`8083`. Erlauben Sie den Zugriff ausschließlich aus dem vertrauenswürdigen LAN und geben Sie den
Port nicht für das Internet frei.

## 2. Image-Variante

Die bereitgestellte `compose.yaml` verwendet das aktuelle vorgefertigte öffentliche Image und
speichert dauerhafte Daten im Verzeichnis `./data`. Sie lädt
`docker.io/macsobeck/trovis-proxy:latest` von Docker Hub für AMD64 oder ARM64 und erstellt bei der
Installation nicht das `Dockerfile` des Repositorys neu.

Das `Dockerfile` bleibt für die Projektentwicklung und die Veröffentlichung neuer Images erhalten,
nicht für die Standardinstallation.

## 3. Projektdateien beziehen

Für eine neue Installation:

```bash
git clone https://github.com/macsobeck/trovis-proxy.git
cd trovis-proxy
```

Wenn das Repository bereits vorhanden ist, öffnen Sie ein Terminal in dessen Stammverzeichnis.
Die Installation verwendet `compose.yaml`.

## 4. Dauerhafte Speicherung vorbereiten

Die Compose-Datei speichert die Konfiguration im Host-Verzeichnis `./data`. Erstellen Sie es, bevor
Sie den Modbus Proxy starten:

```bash
mkdir -p data
sudo chown -R 1000:1000 data
sudo chmod 755 data
```

Die veröffentlichten Images laufen mit der festen UID und GID `1000`. Die Befehle stellen auf
Linux- und NAS-Systemen den erforderlichen Schreibzugriff bereit.

## 5. Image laden

Prüfen Sie die Standard-Compose-Datei und laden Sie das aktuelle öffentliche
Multi-Plattform-Image. Eine Anmeldung bei der Registry ist nicht erforderlich; Docker wählt
automatisch Linux AMD64 oder ARM64 aus.

```bash
docker compose config --quiet
docker compose pull
```

Die Image-Referenz lautet:

```text
docker.io/macsobeck/trovis-proxy:latest
```

Das Image enthält die optionale Abhängigkeit für Serial RTU. Die Standardports sind:

| Zweck | Host-Bindung | Container-Port |
|---|---|---:|
| Modbus-TCP-Listener für Client-Anwendungen | alle Schnittstellen, Port `7112` | `7112` |
| Administrationsoberfläche | alle Schnittstellen, Port `8083` | `8080` |

## 6. Modbus Proxy starten

Starten Sie das Image im Hintergrund:

```bash
docker compose up -d
docker compose ps
```

Prüfen Sie, ob der Modbus Proxy betriebsbereit ist:

```bash
curl http://127.0.0.1:8083/health
```

Der Health-Endpunkt sollte Folgendes zurückgeben:

```json
{"status":"ok"}
```

Wenn der Start fehlschlägt, prüfen Sie die Protokolle:

```bash
docker compose logs --tail=100 trovis-proxy
```

## 7. Administrationsoberfläche öffnen

Öffnen Sie von einem Rechner im vertrauenswürdigen LAN:

```text
http://NAS-IP:8083/
```

Ersetzen Sie `NAS-IP` durch die IP-Adresse oder den vertrauenswürdigen DNS-Namen des Docker-Hosts.
Beschränken Sie den Zugriff in der Host-Firewall auf die erforderlichen LAN-Clients.

## 8. Reglerprofil erstellen

Öffnen Sie **Controller connection** und wählen Sie **New profile**. Tragen Sie die Einstellungen
für die Verbindung vom Modbus Proxy zum Regler ein:

1. Geben Sie einen Profilnamen und optional eine Beschreibung ein.
2. Wählen Sie `Modbus TCP`, `RTU-over-TCP` oder `Serial RTU`.
3. Geben Sie bei einem TCP-Transport Host und Port des Reglers oder Adapters ein.
4. Geben Sie die Modbus-Stationsadresse des Reglers ein. Der Standardwert ist `247`, muss jedoch
   mit dem tatsächlichen Regler übereinstimmen.
5. Speichern Sie optional den Zugriffsschlüssel. Er verbleibt im Pass-through-Modus und wird nicht
   in den Modbus-Datenverkehr eingefügt.
6. Wählen Sie unter **Client scheduling** die Option **Multi-client incl. TROVIS-VIEW**,
   wenn Sie TROVIS-VIEW einsetzen, oder **Multi-client without TROVIS-VIEW** für zyklische
   Abfragen etwa aus Home Assistant und Node-RED. Unter **Custom** geben Sie eine eigene Dauer ein.
7. Wenn Regler oder Adapter andere Timing-Werte benötigen, öffnen Sie **Advanced communication
   settings**. Der **Total timeout** von `16 s` umfasst auch die Wartezeit in der Warteschlange.
   **Maximum TCP connection age** von `25 s` plant die Erneuerung an der nächsten Sequenzgrenze.
   Details stehen unter [Timing-Voreinstellungen](configuration.md#timing-presets).
8. Prüfen Sie die Grenzen für Wiederholungen bei Lese- und Schreibanfragen.
9. Wählen Sie **Save**.
10. Wählen Sie **Activate**, wenn dieses Profil noch nicht aktiv ist.

Es kann jeweils nur ein Profil aktiv sein. Ein Wechsel des aktiven Profils erfordert weder einen
neuen Build noch einen Neustart des Containers.

### Serieller USR-Ethernet-Adapter

Konfigurieren Sie Socket A eines USR-Adapters für einen zuverlässigen Betrieb wie folgt:

- **Work Mode** auf `TCP Server` setzen;
- den benachbarten Protokollmodus auf `None` und nicht auf `ModbusTCP` setzen;
- im Profil des Modbus Proxy `RTU-over-TCP` als Transport auswählen.

Dadurch bleibt der USR-Adapter transparent, während der Modbus Proxy die erforderliche
Modbus-TCP-zu-RTU-Rahmung ausführt.

## 9. Reglerverbindung testen

Wählen Sie **Test connection**. Der Test öffnet den konfigurierten Transport und meldet Ziel,
Station und Verbindungszeit. Er sendet absichtlich keine beliebige Modbus-Registeranfrage.

Eine erfolgreiche TCP-Verbindung bestätigt nur die Erreichbarkeit im Netzwerk. Sie belegt nicht,
dass der Regler einen bestimmten Modbus-Funktionscode oder eine bestimmte Adresse akzeptiert.

## 10. Client-Anwendungen verbinden

Wählen Sie in jeder Client-Anwendung **Modbus TCP** als Verbindungsart. Verwenden Sie die
IP-Adresse oder den DNS-Namen des Docker-Hosts und Port `7112`. In TROVIS-VIEW verwenden Sie
die vom Projekt benötigte Stationsadresse.

Der Proxy erfasst die vom Client gesendete Unit ID. Für Anfragen an den Regler verwendet er die
im aktiven Reglerprofil konfigurierte Stationsadresse.

Erlauben Sie eingehenden TCP-Verkehr auf Port `7112` in der Host-Firewall nur von den Systemen,
auf denen Ihre Client-Anwendungen laufen.

## 11. Betrieb prüfen

Öffnen Sie die Seite **Status** und prüfen Sie:

- Listener-Adresse und -Port;
- aktives Profil und Reglerziel;
- verbundene Modbus-TCP-Clients;
- Zähler für Anfragen, Zeitüberschreitungen, Wiederholungen und Neuverbindungen.

Die Seite aktualisiert sich alle fünf Sekunden. Wählen Sie **Reset counters** und bestätigen Sie,
um im laufenden Betrieb einen neuen Messzeitraum zu starten.

Verfolgen Sie bei der Diagnose die laufenden Protokolle:

```bash
docker compose logs -f trovis-proxy
```

Die aktuelle NAS-Compose-Konfiguration aktiviert mit `MODBUS_TRACE=1` die Aufzeichnung roher
Modbus-PDUs zur Diagnose. Die Protokolle können Protokolldaten enthalten. Setzen Sie den Wert nach
der Fehlerbehebung auf `0` und erstellen Sie den Container neu:

```bash
docker compose up -d --force-recreate
```

## 12. Dauerhafte Speicherung und Sicherungen

Profile werden auf dem Docker-Host in `./data/config.json` gespeichert und im Container als
`/data/config.json` eingebunden. Normale Neustarts, Image-Updates und `docker compose down` erhalten
dieses per Bind-Mount eingebundene Verzeichnis.

Erstellen Sie nach der Konfiguration des Modbus Proxy eine Sicherung.

```bash
docker compose exec -T trovis-proxy sh -c 'cat /data/config.json' > modbus-proxy-config-backup.json
chmod 600 modbus-proxy-config-backup.json
```

Die Sicherung enthält den gespeicherten Zugriffsschlüssel im Klartext. Schützen Sie sie
entsprechend.

Stellen Sie eine Sicherung wie folgt wieder her:

```bash
docker compose stop trovis-proxy
docker compose run --rm --no-deps -T --entrypoint sh trovis-proxy \
  -c 'umask 077; cat > /data/config.json' < modbus-proxy-config-backup.json
docker compose up -d
```

## 13. Installation aktualisieren

Sichern Sie zuerst die Konfiguration. Falls der Dienst in der bisherigen Compose-Datei
`gateway` heißt, führen Sie vor der Aktualisierung mit dieser Datei `docker compose down` aus.
So werden die Host-Ports für den umbenannten Dienst frei. Aktualisieren Sie anschließend
die Standardinstallation auf das aktuelle Image:

```bash
git pull --ff-only
docker compose pull
docker compose up -d
docker compose ps
```

Das per Bind-Mount eingebundene Verzeichnis `./data` bleibt mit dem Ersatzcontainer verbunden.

## 14. Serial RTU mit Docker

Fügen Sie unter Linux innerhalb von `services.trovis-proxy` in `compose.yaml` Folgendes hinzu, um das
serielle Gerät an den Container durchzureichen:

```yaml
devices:
  - "/dev/ttyUSB0:/dev/ttyUSB0"
```

Der Container-Benutzer benötigt die Berechtigung zum Öffnen des Geräts. Eigentümer und
Gruppen-IDs unterscheiden sich zwischen Linux-Distributionen. Prüfen Sie sie mit:

```bash
ls -l /dev/ttyUSB0
```

Das veröffentlichte Image verwendet die feste Gruppen-ID `1000`. Wenn das serielle Gerät eine
andere Gruppen-ID benötigt, erstellen Sie ein angepasstes Entwicklungs-Image aus dem `Dockerfile`.
Dies liegt außerhalb des Standard-Installationsablaufs.

Der direkte Zugriff auf serielle USB-Geräte über Docker Desktop hängt von der USB-Weiterleitung
des Hosts ab. Unter macOS oder Windows ist die native Installation oder ein RTU-over-TCP-Adapter
häufig einfacher.

## 15. Native Python-Installation

Im Stammverzeichnis des Repositorys:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[serial]'
mkdir -p data
trovis-gateway \
  --listen-host 0.0.0.0 \
  --listen-port 7112 \
  --admin-host 127.0.0.1 \
  --admin-port 8080 \
  --config-path "$PWD/data/config.json"
```

Lassen Sie dieses Terminal während des Tests geöffnet. Beenden Sie den Modbus Proxy mit `Ctrl+C`.
Führen Sie denselben Befehl für eine dauerhafte native Installation über einen Service-Manager und
mit einem absoluten Konfigurationspfad aus.

## 16. Fehlerbehebung

### Die Website lässt sich nicht öffnen

Prüfen Sie den Containerstatus und die Protokolle des Modbus Proxy mit dem Compose-Befehl für die
gewählte Image-Variante. Stellen Sie außerdem sicher, dass kein anderer Prozess Host-Port `8083`
verwendet.

### Ein Modbus-TCP-Client kann keine Verbindung herstellen

Prüfen Sie die Modbus-TCP-Einstellungen des Clients. Läuft die Anwendung auf einem separaten
Gerät, verwenden Sie die LAN-Adresse oder den DNS-Namen des Docker-Hosts. Prüfen Sie außerdem,
ob die Host-Firewall TCP-Port `7112` freigibt.

### Der Reglertest schlägt fehl

Prüfen Sie aktives Profil, Host und Port des Reglers, Routing und Adaptermodus. Stellen Sie bei
einem USR-Adapter Socket A auf `TCP Server` mit Protokollmodus `None` und wählen Sie im Modbus Proxy
`RTU-over-TCP`. Der Adapter muss rohe Modbus-RTU-Rahmen transportieren, statt sie in Modbus TCP
umzuwandeln.

### DNS und Netzwerkerreichbarkeit prüfen

**Test connection** zeigt die Dauer der DNS-Auflösung, des TCP-Aufbaus und die erreichte
IP-Adresse an. Ersetzen Sie `trovis-proxy-local` und `trovis.example.test` durch Ihren
Containernamen und den Hostnamen des Adapters.

```bash
docker exec trovis-proxy-local nslookup trovis.example.test
docker exec trovis-proxy-local dig trovis.example.test A
docker exec trovis-proxy-local dig trovis.example.test AAAA
docker exec trovis-proxy-local ping -c 3 trovis.example.test
docker exec trovis-proxy-local traceroute trovis.example.test
```

Bei einem kurzen Hostnamen berücksichtigt `dig +search` die Suchdomänen des Containers.
`ping` setzt voraus, dass der Container einen ICMP-Socket öffnen darf und das Ziel auf ICMP
antwortet. Der Standardmodus von `traceroute` verwendet UDP und ist auf ICMP-Antworten entlang
der Route angewiesen. Ob der Adapter-Port erreichbar ist, zeigt der TCP-Test im Web-UI.

### Anfragen liefern die Modbus-Ausnahme `0x0B`

Der Regler antwortet nicht oder es ist kein aktives Profil konfiguriert. Prüfen Sie die
Statuszähler und die Protokolle des Modbus Proxy.

### Serial RTU funktioniert nicht

Prüfen Sie Gerätepfad, Gerätezuordnung zum Container, Host-Berechtigungen, Baudrate, Datenbits,
Parität, Stoppbits und Modbus-Stationsadresse.
