# LKW-Bot Installation auf Raspberry Pi

## Voraussetzungen

- Raspberry Pi (3B+ oder neuer empfohlen)
- Raspbian OS installiert
- Internetzugang
- SSH-Zugang eingerichtet

## 1. System-Updates

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

## 2. Python und benötigte Pakete installieren

```bash
# Python 3 und pip
sudo apt-get install -y python3 python3-pip

# ADB (Android Debug Bridge)
sudo apt-get install -y adb

# Tesseract OCR
sudo apt-get install -y tesseract-ocr tesseract-ocr-deu

# OpenCV Abhängigkeiten
sudo apt-get install -y libatlas-base-dev libhdf5-dev libhdf5-serial-dev \
    libatlas-base-dev libjasper-dev libqtgui4 libqt4-test
```

## 3. Python-Bibliotheken installieren

```bash
cd /home/pi/lkw-bot
pip3 install -r requirements.txt
```

## 4. SSH-Schlüssel für VMOSCloud einrichten (optional)

Falls du SSH-Keys statt Passwort nutzen möchtest:

```bash
# SSH-Schlüssel generieren (falls noch nicht vorhanden)
ssh-keygen -t rsa -b 4096

# Public Key zu VMOSCloud hinzufügen (manuell)
cat ~/.ssh/id_rsa.pub
```

## 5. Dateien vorbereiten

Stelle sicher, dass folgende Dateien im Projektverzeichnis sind:
- `lkw_bot_web.py` (Hauptskript)
- `rentier_template.png` (Template-Bild für LKW-Erkennung)
- `templates/login.html`
- `templates/index.html`

## 6. Konfiguration anpassen

Öffne `lkw_bot_web.py` und passe folgende Werte an:

### SSH-Verbindung (Zeilen 28-33):
```python
SSH_HOST = "10.0.8.67_1762116558169@103.237.100.130"
SSH_PORT = 1824
SSH_KEY = "dein-ssh-schlüssel-hier"  # Optional
LOCAL_ADB_PORT = 5839
REMOTE_ADB = "adb-proxy:24345"
```

### Sicherheit (Zeile 40):
```python
app.secret_key = 'ÄNDERE-DIESEN-SCHLÜSSEL-ZU-ETWAS-ZUFÄLLIGEM'
```

### Login-Daten (Zeilen 317-319):
```python
users_db = {
    'admin': User('1', 'admin', generate_password_hash('DEIN-SICHERES-PASSWORT'))
}
```

**WICHTIG:** Ändere das Standard-Passwort!

## 7. Koordinaten-Anpassung (falls nötig)

Die Koordinaten sind bereits für 720x1280 umgerechnet. Falls dein Gerät eine andere Auflösung hat:

```python
# Im Skript anpassen (Zeilen 18-28)
COORDS_NEW = {
    'esc': (x, y),
    'share': (x, y),
    # ... etc
}
```

## 8. Bot als Systemdienst einrichten (empfohlen)

Erstelle eine Systemd-Service-Datei:

```bash
sudo nano /etc/systemd/system/lkw-bot.service
```

Inhalt:
```ini
[Unit]
Description=LKW Bot Web Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/lkw-bot
ExecStart=/usr/bin/python3 /home/pi/lkw-bot/lkw_bot_web.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Dienst aktivieren und starten:
```bash
sudo systemctl daemon-reload
sudo systemctl enable lkw-bot.service
sudo systemctl start lkw-bot.service
```

Status prüfen:
```bash
sudo systemctl status lkw-bot.service
```

Logs anzeigen:
```bash
sudo journalctl -u lkw-bot.service -f
```

## 9. Firewall konfigurieren (optional)

Falls UFW aktiv ist:
```bash
sudo ufw allow 5000/tcp
```

## 10. Bot starten (manuell)

```bash
cd /home/pi/lkw-bot
python3 lkw_bot_web.py
```

## 11. Zugriff auf Web-Interface

### Lokal (auf dem Raspberry Pi):
```
http://localhost:5000
```

### Im Netzwerk:
```
http://[RASPBERRY-PI-IP]:5000
```

IP-Adresse herausfinden:
```bash
hostname -I
```

### Von außen (Internet):

Du musst Port-Forwarding in deinem Router einrichten:
- Weiterleitung von einem externen Port (z.B. 8080) auf Port 5000 des Raspberry Pi
- Dann zugriff über: `http://[DEINE-EXTERNE-IP]:8080`

**Sicherheitshinweis:** Für Internet-Zugriff solltest du HTTPS einrichten (siehe unten)

## 12. HTTPS einrichten (für Internet-Zugriff empfohlen)

### Mit Let's Encrypt und Nginx:

```bash
# Nginx installieren
sudo apt-get install -y nginx

# Certbot installieren
sudo apt-get install -y certbot python3-certbot-nginx

# Nginx konfigurieren
sudo nano /etc/nginx/sites-available/lkw-bot
```

Nginx-Konfiguration:
```nginx
server {
    listen 80;
    server_name deine-domain.de;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Konfiguration aktivieren
sudo ln -s /etc/nginx/sites-available/lkw-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# SSL-Zertifikat erstellen
sudo certbot --nginx -d deine-domain.de
```

## Troubleshooting

### SSH-Tunnel funktioniert nicht:
```bash
# Manuelle Verbindung testen
ssh -oHostKeyAlgorithms=+ssh-rsa 10.0.8.67_1762116558169@103.237.100.130 -p 1824
```

### ADB verbindet nicht:
```bash
# ADB-Server neu starten
adb kill-server
adb start-server

# Verbindung testen
adb connect localhost:5839
adb devices
```

### OCR erkennt Text nicht:
```bash
# Tesseract-Sprachen installieren
sudo apt-get install tesseract-ocr-eng tesseract-ocr-deu

# OCR testen
tesseract staerke_ocr.png stdout
```

### Port bereits belegt:
```bash
# Prüfen welcher Prozess Port 5000 nutzt
sudo lsof -i :5000

# Prozess beenden
sudo kill -9 [PID]
```

## Wartung

### Logs ansehen:
```bash
sudo journalctl -u lkw-bot.service -f
```

### Dienst neu starten:
```bash
sudo systemctl restart lkw-bot.service
```

### Dienst stoppen:
```bash
sudo systemctl stop lkw-bot.service
```

### Updates einspielen:
```bash
cd /home/pi/lkw-bot
git pull  # falls du Git verwendest
sudo systemctl restart lkw-bot.service
```

## Sicherheits-Checkliste

- [ ] Standard-Passwort in lkw_bot_web.py geändert
- [ ] app.secret_key geändert
- [ ] Firewall konfiguriert
- [ ] SSH-Keys statt Passwörter verwenden
- [ ] Starke Passwörter verwenden
- [ ] HTTPS für Internet-Zugriff eingerichtet
- [ ] Regelmäßige Updates installieren
- [ ] Backup-Strategie eingerichtet

## Performance-Tipps

### Raspberry Pi optimieren:
```bash
# GPU-Memory erhöhen (für OpenCV)
sudo raspi-config
# -> Performance Options -> GPU Memory -> 128
```

### Python-Prozess priorisieren:
```bash
# In der systemd-Service-Datei hinzufügen:
Nice=-10
```

## Backup

```bash
# Wichtige Dateien sichern
cd /home/pi
tar -czf lkw-bot-backup-$(date +%Y%m%d).tar.gz lkw-bot/

# Auf anderen Rechner kopieren
scp lkw-bot-backup-*.tar.gz user@backup-server:/backup/
```

## Support

Bei Problemen:
1. Logs prüfen: `sudo journalctl -u lkw-bot.service -n 100`
2. System-Ressourcen prüfen: `htop`
3. Netzwerk prüfen: `ping 103.237.100.130`
4. ADB-Verbindung prüfen: `adb devices`