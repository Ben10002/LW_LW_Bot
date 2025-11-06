#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LKW-Bot für Last War mit Web-Interface
Optimiert für Raspberry Pi und VMOSCloud über SSH-Tunnel
"""

import subprocess
import time
import cv2
import numpy as np
from PIL import Image
import pytesseract
import os
import re
import threading
import json
from datetime import datetime
import pytz
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import logging

# Übersetzungen
TRANSLATIONS = {
    'de': {
        'app_title': 'LKW-Bot Steuerung',
        'app_subtitle': 'VMOSCloud Edition für Raspberry Pi',
        'logout': 'Abmelden',
        'status': 'Status',
        'loading': 'Lade...',
        'adb_connected': 'ADB: Verbunden',
        'adb_disconnected': 'ADB: Getrennt',
        'btn_start': 'Start',
        'btn_pause': 'Pause',
        'btn_stop': 'Stopp',
        'statistics': 'Statistiken',
        'processed': 'Verarbeitet',
        'shared': 'Geteilt',
        'skipped': 'Übersprungen',
        'reset_stats': 'Statistiken zurücksetzen',
        'settings': 'Einstellungen',
        'use_strength_limit': 'Stärkebeschränkung nutzen',
        'max_strength': 'Maximale Stärke (M)',
        'filter_server': 'Server filtern',
        'server_number': 'Servernummer',
        'reset_interval': 'Reset-Intervall (Minuten)',
        'share_mode': 'Teilen in',
        'share_world': 'Weltchat',
        'share_alliance': 'A4O',
        'save_settings': 'Einstellungen speichern',
        'login_title': 'LKW-Bot',
        'username': 'Benutzername',
        'password': 'Passwort',
        'login_button': 'Anmelden',
        'login_info': 'Last War LKW-Sharing Bot',
        'login_subtitle': 'VMOSCloud Edition',
        'invalid_credentials': 'Ungültige Anmeldedaten',
        'stopped': 'Gestoppt',
        'running': 'Läuft',
        'paused': 'Pausiert',
        'no_action': 'Keine Aktion',
        'settings_saved': 'Einstellungen gespeichert!',
        'confirm_reset': 'Statistiken wirklich zurücksetzen?',
        'language': 'Sprache',
        'admin_dashboard': 'Admin'
    },
    'en': {
        'app_title': 'Truck Bot Control',
        'app_subtitle': 'VMOSCloud Edition for Raspberry Pi',
        'logout': 'Logout',
        'status': 'Status',
        'loading': 'Loading...',
        'adb_connected': 'ADB: Connected',
        'adb_disconnected': 'ADB: Disconnected',
        'btn_start': 'Start',
        'btn_pause': 'Pause',
        'btn_stop': 'Stop',
        'statistics': 'Statistics',
        'processed': 'Processed',
        'shared': 'Shared',
        'skipped': 'Skipped',
        'reset_stats': 'Reset Statistics',
        'settings': 'Settings',
        'use_strength_limit': 'Use strength limit',
        'max_strength': 'Maximum Strength (M)',
        'filter_server': 'Filter server',
        'server_number': 'Server number',
        'reset_interval': 'Reset interval (minutes)',
        'share_mode': 'Share in',
        'share_world': 'World Chat',
        'share_alliance': 'A4O',
        'save_settings': 'Save Settings',
        'login_title': 'Truck Bot',
        'username': 'Username',
        'password': 'Password',
        'login_button': 'Login',
        'login_info': 'Last War Truck Sharing Bot',
        'login_subtitle': 'VMOSCloud Edition',
        'invalid_credentials': 'Invalid credentials',
        'stopped': 'Stopped',
        'running': 'Running',
        'paused': 'Paused',
        'no_action': 'No action',
        'settings_saved': 'Settings saved!',
        'confirm_reset': 'Really reset statistics?',
        'language': 'Language',
        'admin_dashboard': 'Admin'
    }
}

# Konfiguration
TEMPLATE_PATH = 'rentier_template.png'
STAERKENFILE = "lkw_staerken.txt"

# Koordinaten umgerechnet von 1600x900 auf 720x1280
# Umrechnungsfaktor: x * 0.45, y * 1.422
COORDS_OLD = {
    'esc': (840, 100),
    'share': (530, 1400),
    'share_confirm1': (300, 550),
    'share_confirm2': (520, 900),
}

COORDS_NEW = {
    'esc': (680, 70),             # ESC-Button oben rechts
    'share': (450, 1100),         # Teilen-Button
    'share_confirm1': (300, 450), # Bestätigung 1 - Weltchat
    'share_confirm2': (400, 750), # Bestätigung 2 - Weltchat
}

# Koordinaten für Allianz-Chat (Alternative)
COORDS_ALLIANCE = {
    'esc': (680, 70),             # ESC-Button (gleich)
    'share': (450, 1100),         # Teilen-Button (gleich)
    'share_confirm1': (300, 700), # Bestätigung 1 - Allianz-Chat
    'share_confirm2': (400, 750), # Bestätigung 2 - Allianz-Chat (gleich)
}

# OCR-Boxen (links, oben, rechts, unten)
STAERKE_BOX = (200, 950, 300, 1000)   # Stärke-Bereich
SERVER_BOX = (160, 860, 220, 915)     # Server-Bereich

# SSH-Tunnel Konfiguration für VMOSCloud
SSH_HOST = "10.0.4.206_1762383884162@103.237.100.130"
SSH_PORT = 1824
SSH_KEY = "j0343aTw718AKRn2XP018+mmc8PkBtBdLN7Pqg7c/eWZ/ZjtMGLTwsdjqmDMsuqd8cDIZKC0oYm0P4eCVLjeAQ=="
LOCAL_ADB_PORT = 9842
REMOTE_ADB = "adb-proxy:46795"

# Flask App Setup
app = Flask(__name__)
app.secret_key = 'dein-geheimer-schluessel-aendern!'  # WICHTIG: Ändern!

# Flask App Setup
app = Flask(__name__)
app.secret_key = 'dein-geheimer-schluessel-aendern!'  # WICHTIG: Ändern!

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== User Management ==================

USERS_FILE = "users.json"
AUDIT_LOG_FILE = "audit_log.json"

class User:
    def __init__(self, username, password_hash, role, blocked=False):
        self.username = username
        self.password_hash = password_hash
        self.role = role  # 'admin', 'user'
        self.blocked = blocked
    
    def is_authenticated(self):
        return True
    
    def is_active(self):
        return not self.blocked
    
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return self.username

def init_users():
    """Initialisiere User-Datenbank"""
    if not os.path.exists(USERS_FILE):
        users = {
            'admin': {
                'password': generate_password_hash('rREq8/1F4m#'),
                'role': 'admin',
                'blocked': False
            },
            'All4One': {
                'password': generate_password_hash('52B1z_'),
                'role': 'user',
                'blocked': False
            },
            'Server39': {
                'password': generate_password_hash('!3Z4d5'),
                'role': 'user',
                'blocked': False
            }
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)

def load_users():
    """Lade User-Datenbank"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    """Speichere User-Datenbank"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def log_audit(username, action, details=""):
    """Log Benutzeraktionen"""
    if not os.path.exists(AUDIT_LOG_FILE):
        logs = []
    else:
        with open(AUDIT_LOG_FILE, 'r') as f:
            logs = json.load(f)
    
    from datetime import datetime
    import pytz
    
    # Deutsche Zeit
    tz = pytz.timezone('Europe/Berlin')
    timestamp = datetime.now(tz).strftime('%d.%m.%Y %H:%M:%S')
    
    logs.append({
        'username': username,
        'action': action,
        'details': details,
        'timestamp': timestamp
    })
    
    # Nur letzte 500 Einträge behalten
    logs = logs[-500:]
    
    with open(AUDIT_LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

@login_manager.user_loader
def load_user(username):
    users = load_users()
    if username in users:
        user_data = users[username]
        return User(username, user_data['password'], user_data['role'], user_data.get('blocked', False))
    return None

# Initialisiere Users beim Start
init_users()

# ================== Bot-Steuerung ==================

class BotController:
    def __init__(self):
        self.running = False
        self.paused = False
        self.thread = None
        self.ssh_process = None
        self.status = "Gestoppt"
        self.last_action = ""
        self.lock = threading.Lock()  # Thread-Lock für Queue
        self.current_user = None  # Aktuell aktiver User
        
        # Einstellungen
        self.use_limit = False
        self.strength_limit = 60.0
        self.use_server_filter = False
        self.server_number = "49"
        self.reset_interval = 15  # Minuten
        self.share_mode = "world"  # "world" oder "alliance" - für zukünftige Erweiterung
        self.adb_connected = False
        
        # Statistiken
        self.trucks_processed = 0
        self.trucks_shared = 0
        self.trucks_skipped = 0
        
    def setup_ssh_tunnel(self):
        """Erstellt SSH-Tunnel zu VMOSCloud"""
        try:
            # Prüfe ob Tunnel bereits läuft
            result = subprocess.run(['pgrep', '-f', f':{LOCAL_ADB_PORT}:'], 
                                  capture_output=True, text=True)
            if result.stdout:
                logger.info("SSH-Tunnel läuft bereits")
                return True
            
            # Starte SSH-Tunnel
            cmd = [
                'ssh',
                '-oHostKeyAlgorithms=+ssh-rsa',
                '-oStrictHostKeyChecking=no',
                '-oServerAliveInterval=60',
                '-oServerAliveCountMax=3',
                SSH_HOST,
                '-p', str(SSH_PORT),
                '-L', f'{LOCAL_ADB_PORT}:{REMOTE_ADB}',
                '-Nf'
            ]
            
            logger.info("Starte SSH-Tunnel...")
            self.ssh_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(3)  # Warte auf Verbindungsaufbau
            
            # Verbinde ADB
            adb_cmd = ['adb', 'connect', f'localhost:{LOCAL_ADB_PORT}']
            result = subprocess.run(adb_cmd, capture_output=True, text=True)
            
            if 'connected' in result.stdout.lower():
                logger.info("ADB erfolgreich verbunden")
                self.adb_connected = True
                return True
            else:
                logger.error(f"ADB-Verbindung fehlgeschlagen: {result.stdout}")
                return False
                
        except Exception as e:
            logger.error(f"SSH-Tunnel-Fehler: {e}")
            return False
    
    def close_ssh_tunnel(self):
        """Schließt SSH-Tunnel"""
        try:
            # Trenne ADB
            subprocess.run(['adb', 'disconnect', f'localhost:{LOCAL_ADB_PORT}'])
            
            # Beende SSH-Prozess
            subprocess.run(['pkill', '-f', f':{LOCAL_ADB_PORT}:'])
            logger.info("SSH-Tunnel geschlossen")
            self.adb_connected = False
        except Exception as e:
            logger.error(f"Fehler beim Schließen des Tunnels: {e}")
    
    def make_screenshot(self, filename='screen.png'):
        """Erstellt Screenshot über ADB"""
        try:
            adb_device = f'localhost:{LOCAL_ADB_PORT}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'screencap', '-p', f'/sdcard/{filename}'], 
                         timeout=10)
            subprocess.run(['adb', '-s', adb_device, 'pull', f'/sdcard/{filename}', filename], 
                         timeout=10)
            return os.path.exists(filename)
        except Exception as e:
            logger.error(f"Screenshot-Fehler: {e}")
            return False
    
    def click(self, x, y):
        """Klickt auf Koordinaten"""
        try:
            adb_device = f'localhost:{LOCAL_ADB_PORT}'
            logger.info(f"Klicke auf ({x}, {y})")
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'tap', str(x), str(y)], 
                         timeout=5)
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"Klick-Fehler: {e}")
            return False
    
    def ocr_staerke(self):
        """Liest Stärke per OCR"""
        try:
            img = Image.open('info.png')
            staerke_img = img.crop(STAERKE_BOX)
            staerke_img.save('staerke_ocr.png')
            
            # OCR mit mehreren Konfigurationen versuchen
            configs = [
                '--psm 7',  # Single text line
                '--psm 8',  # Single word
                '--psm 6',  # Uniform block of text
            ]
            
            for config in configs:
                wert = pytesseract.image_to_string(staerke_img, lang='eng', config=config).strip()
                if wert and ('m' in wert.lower() or 'M' in wert):
                    logger.info(f"OCR Stärke: {wert}")
                    return wert
            
            logger.warning("OCR konnte keine Stärke finden")
            return ""
        except Exception as e:
            logger.error(f"OCR-Fehler: {e}")
            return ""
    
    def ist_server_passend(self):
        """Prüft ob Server passt"""
        try:
            img = Image.open('info.png')
            server_img = img.crop(SERVER_BOX)
            server_img.save('server_ocr.png')
            server_text = pytesseract.image_to_string(server_img, lang='eng').strip()
            logger.info(f"OCR Server: '{server_text}'")
            
            s_txt = server_text.replace(' ', '').replace('O', '0')
            return (f"#{self.server_number}" in s_txt) or (self.server_number in s_txt)
        except Exception as e:
            logger.error(f"Server-Check-Fehler: {e}")
            return False
    
    def rentier_lkw_finden(self):
        """Findet Rentier-LKW per Template-Matching"""
        try:
            screenshot = cv2.imread('screen.png')
            template = cv2.imread(TEMPLATE_PATH)
            
            if screenshot is None or template is None:
                logger.error("Screenshot oder Template fehlt!")
                return None
            
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= 0.40)
            matches = [(int(pt[0]), int(pt[1])) for pt in zip(*locations[::-1])]
            
            return matches if matches else None
        except Exception as e:
            logger.error(f"Template-Matching-Fehler: {e}")
            return None
    
    def staerke_float_wert(self, staerke_text):
        """Extrahiert numerischen Wert aus Stärke-Text und korrigiert fehlendes Komma"""
        match = re.search(r"([\d\.,]+)\s*[mM]", staerke_text)
        if match:
            try:
                zahl_str = match.group(1).replace(',', '.')
                zahl = float(zahl_str)
                
                # Automatische Komma-Korrektur:
                # Wenn die Zahl >= 100 ist UND kein Komma/Punkt drin war
                # dann wurde das Komma vom OCR übersehen
                if zahl >= 100 and '.' not in match.group(1) and ',' not in match.group(1):
                    # Füge Komma zwischen vorletzter und letzter Ziffer ein
                    # 305 → 30.5, 793 → 79.3, 1234 → 123.4
                    zahl = zahl / 10
                    logger.info(f"Komma-Korrektur: {match.group(1)}M → {zahl}M")
                
                return zahl
            except ValueError:
                return None
        return None
    
    def staerke_ist_bekannt(self, staerke):
        """Prüft ob Stärke schon bekannt"""
        if os.path.exists(STAERKENFILE):
            with open(STAERKENFILE, encoding="utf-8") as f:
                if staerke in (line.strip() for line in f):
                    return True
        return False
    
    def notiere_staerke(self, staerke):
        """Notiert Stärke in Datei"""
        with open(STAERKENFILE, "a", encoding="utf-8") as f:
            f.write(staerke + "\n")
        logger.info(f"Stärke {staerke} notiert")
    
    def reset_staerken(self):
        """Löscht Stärken-Liste"""
        try:
            with open(STAERKENFILE, "w", encoding="utf-8") as f:
                f.write("")
            logger.info("Stärken-Liste zurückgesetzt")
        except Exception as e:
            logger.error(f"Reset-Fehler: {e}")
    
    def bot_loop(self):
        """Hauptschleife des Bots"""
        logger.info("Bot-Schleife gestartet")
        
        # Setup SSH-Tunnel
        if not self.setup_ssh_tunnel():
            self.status = "Fehler: SSH-Tunnel konnte nicht aufgebaut werden"
            self.running = False
            return
        
        # Reset-Timer starten
        reset_thread = threading.Thread(target=self.reset_timer, daemon=True)
        reset_thread.start()
        
        while self.running:
            if self.paused:
                self.status = "Pausiert"
                time.sleep(1)
                continue
            
            try:
                self.status = "Läuft - Suche LKWs..."
                self.last_action = "Screenshot erstellen"
                
                if not self.make_screenshot('screen.png'):
                    self.last_action = "Fehler: Screenshot fehlgeschlagen"
                    time.sleep(5)
                    continue
                
                time.sleep(0.5)
                treffer = self.rentier_lkw_finden()
                
                if not treffer:
                    self.last_action = "Kein LKW gefunden - ESC"
                    self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1])
                    self.trucks_processed += 1
                    continue
                
                self.last_action = f"LKW gefunden bei {treffer[0]}"
                logger.info(f"Treffer bei: {treffer[0]}")
                
                # Klicke auf LKW (mit Offset)
                lx = treffer[0][0] + 5  # Angepasster Offset für kleineren Screen
                ly = treffer[0][1] + 5
                self.click(lx, ly)
                
                if not self.make_screenshot('info.png'):
                    self.last_action = "Fehler: Info-Screenshot fehlgeschlagen"
                    continue
                
                # Server-Check
                if self.use_server_filter:
                    self.last_action = "Prüfe Server..."
                    if not self.ist_server_passend():
                        self.last_action = f"Falscher Server - ESC"
                        self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1])
                        self.trucks_skipped += 1
                        self.trucks_processed += 1
                        continue
                
                # Stärke auslesen
                self.last_action = "Lese Stärke..."
                staerke = self.ocr_staerke()
                wert = self.staerke_float_wert(staerke)
                logger.info(f"Stärke gelesen: '{staerke}' Wert: {wert}")
                
                # Stärke-Check
                limit_passed = True
                if self.use_limit and wert is not None:
                    if wert > self.strength_limit:
                        limit_passed = False
                        self.last_action = f"Stärke {wert} > {self.strength_limit} - übersprungen"
                
                if wert is None or not limit_passed or self.staerke_ist_bekannt(staerke):
                    if wert is None:
                        # Keine Stärke erkannt - Liste neu laden
                        self.last_action = "Keine Stärke erkannt - Lade Liste neu"
                        self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1])
                        time.sleep(0.5)
                        # Zweiter ESC zum Neuladen der LKW-Liste
                        self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1])
                    elif not limit_passed:
                        self.last_action = f"Stärke {wert} > {self.strength_limit} - übersprungen"
                        self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1])
                    else:
                        self.last_action = f"Stärke {staerke} bereits bekannt - übersprungen"
                        self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1])
                    
                    self.trucks_skipped += 1
                    self.trucks_processed += 1
                    continue
                
                # LKW teilen!
                self.last_action = f"Teile LKW (Stärke: {staerke})"
                self.notiere_staerke(staerke)
                
                # Wähle Koordinaten basierend auf share_mode
                if self.share_mode == "alliance":
                    coords = COORDS_ALLIANCE
                    mode_text = "Allianz-Chat"
                else:
                    coords = COORDS_NEW
                    mode_text = "Weltchat"
                
                self.last_action = f"Teile LKW im {mode_text} (Stärke: {staerke})"
                
                self.click(coords['share'][0], coords['share'][1])
                self.click(coords['share_confirm1'][0], coords['share_confirm1'][1])
                self.click(coords['share_confirm2'][0], coords['share_confirm2'][1])
                self.click(coords['esc'][0], coords['esc'][1])
                
                self.trucks_shared += 1
                self.trucks_processed += 1
                self.last_action = f"LKW erfolgreich geteilt! ({self.trucks_shared} gesamt)"
                
            except Exception as e:
                logger.error(f"Fehler in Bot-Schleife: {e}")
                self.last_action = f"Fehler: {str(e)}"
                time.sleep(5)
        
        # Cleanup
        self.close_ssh_tunnel()
        self.status = "Gestoppt"
        logger.info("Bot-Schleife beendet")
    
    def reset_timer(self):
        """Timer für automatischen Reset der Stärken-Liste"""
        while self.running:
            time.sleep(self.reset_interval * 60)
            if self.running:
                self.reset_staerken()
                self.last_action = f"Stärken-Liste nach {self.reset_interval} Min. zurückgesetzt"
    
    def start(self):
        """Startet den Bot"""
        if not self.running:
            self.running = True
            self.paused = False
            self.thread = threading.Thread(target=self.bot_loop, daemon=True)
            self.thread.start()
            logger.info("Bot gestartet")
    
    def pause(self):
        """Pausiert/Fortsetzt den Bot"""
        if self.running:
            self.paused = not self.paused
            logger.info(f"Bot {'pausiert' if self.paused else 'fortgesetzt'}")
    
    def stop(self):
        """Stoppt den Bot"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Bot gestoppt")

# Globale Bot-Instanz
bot = BotController()

# ================== User Management ==================

# ================== Flask Routes ==================

def get_language():
    """Holt die aktuelle Sprache aus der Session"""
    return session.get('language', 'de')

def translate(key):
    """Übersetzt einen Schlüssel in die aktuelle Sprache"""
    lang = get_language()
    return TRANSLATIONS.get(lang, TRANSLATIONS['de']).get(key, key)

@app.route('/set_language/<lang>')
def set_language(lang):
    """Setzt die Sprache"""
    if lang in TRANSLATIONS:
        session['language'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        if username in users:
            user_data = users[username]
            if user_data.get('blocked', False):
                error = "Benutzer ist gesperrt"
                return render_template('login.html', error=error, t=translate, lang=get_language())
            
            if check_password_hash(user_data['password'], password):
                user = User(username, user_data['password'], user_data['role'], user_data.get('blocked', False))
                login_user(user)
                log_audit(username, 'Login', '')
                return redirect(url_for('index'))
        
        error = translate('invalid_credentials')
        return render_template('login.html', error=error, t=translate, lang=get_language())
    
    return render_template('login.html', t=translate, lang=get_language())

@app.route('/logout')
@login_required
def logout():
    log_audit(current_user.username, 'Logout', '')
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', t=translate, lang=get_language(), user=current_user)

@app.route('/api/status')
@login_required
def api_status():
    return jsonify({
        'running': bot.running,
        'paused': bot.paused,
        'status': bot.status,
        'last_action': bot.last_action,
        'trucks_processed': bot.trucks_processed,
        'trucks_shared': bot.trucks_shared,
        'trucks_skipped': bot.trucks_skipped,
        'adb_connected': bot.adb_connected,
        'current_user': bot.current_user
    })

@app.route('/api/start', methods=['POST'])
@login_required
def api_start():
    # Queue-System: Admin hat Priorität
    users = load_users()
    if current_user.username in users and users[current_user.username].get('blocked', False):
        return jsonify({'error': 'User is blocked'}), 403
    
    with bot.lock:
        if bot.current_user and bot.current_user != current_user.username:
            if current_user.role != 'admin':
                return jsonify({'error': f'Bot wird bereits von {bot.current_user} verwendet'}), 409
            # Admin übernimmt
            bot.stop()
        
        bot.current_user = current_user.username
        bot.start()
        log_audit(current_user.username, 'Start Bot', '')
    
    return jsonify({'success': True})

@app.route('/api/pause', methods=['POST'])
@login_required
def api_pause():
    bot.pause()
    log_audit(current_user.username, 'Pause Bot', '')
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    with bot.lock:
        bot.stop()
        bot.current_user = None
        log_audit(current_user.username, 'Stop Bot', '')
    return jsonify({'success': True})

@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def api_settings():
    if request.method == 'POST':
        # Prüfe ob User gesperrt ist
        users = load_users()
        if current_user.username in users and users[current_user.username].get('blocked', False):
            return jsonify({'error': 'User is blocked'}), 403
        
        data = request.json
        bot.use_limit = data.get('use_limit', False)
        bot.strength_limit = float(data.get('strength_limit', 60))
        bot.use_server_filter = data.get('use_server_filter', False)
        bot.server_number = data.get('server_number', '49')
        bot.reset_interval = int(data.get('reset_interval', 15))
        bot.share_mode = data.get('share_mode', 'world')
        
        log_audit(current_user.username, 'Change Settings', f"limit={data.get('use_limit')}, strength={data.get('strength_limit')}, server={data.get('server_number')}, mode={data.get('share_mode')}")
        
        return jsonify({'success': True})
    else:
        return jsonify({
            'use_limit': bot.use_limit,
            'strength_limit': bot.strength_limit,
            'use_server_filter': bot.use_server_filter,
            'server_number': bot.server_number,
            'reset_interval': bot.reset_interval,
            'share_mode': bot.share_mode
        })

@app.route('/api/reset_stats', methods=['POST'])
@login_required
def api_reset_stats():
    bot.trucks_processed = 0
    bot.trucks_shared = 0
    bot.trucks_skipped = 0
    log_audit(current_user.username, 'Reset Statistics', '')
    return jsonify({'success': True})

# ================== Admin Routes ==================

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html', t=translate, lang=get_language(), user=current_user)

@app.route('/api/admin/users', methods=['GET'])
@login_required
def api_admin_get_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    user_list = []
    for username, data in users.items():
        user_list.append({
            'username': username,
            'role': data['role'],
            'blocked': data.get('blocked', False)
        })
    return jsonify({'users': user_list})

@app.route('/api/admin/users/<username>/block', methods=['POST'])
@login_required
def api_admin_block_user(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    if username in users and username != 'admin':
        users[username]['blocked'] = True
        save_users(users)
        log_audit(current_user.username, 'Block User', username)
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/users/<username>/unblock', methods=['POST'])
@login_required
def api_admin_unblock_user(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    if username in users:
        users[username]['blocked'] = False
        save_users(users)
        log_audit(current_user.username, 'Unblock User', username)
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/users', methods=['POST'])
@login_required
def api_admin_add_user():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'user')
    
    users = load_users()
    if username in users:
        return jsonify({'error': 'User already exists'}), 400
    
    users[username] = {
        'password': generate_password_hash(password),
        'role': role,
        'blocked': False
    }
    save_users(users)
    log_audit(current_user.username, 'Add User', username)
    return jsonify({'success': True})

@app.route('/api/admin/users/<username>', methods=['DELETE'])
@login_required
def api_admin_delete_user(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if username == 'admin':
        return jsonify({'error': 'Cannot delete admin'}), 400
    
    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
        log_audit(current_user.username, 'Delete User', username)
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/users/<username>/password', methods=['POST'])
@login_required
def api_admin_change_password(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    new_password = data.get('password')
    
    users = load_users()
    if username in users:
        users[username]['password'] = generate_password_hash(new_password)
        save_users(users)
        log_audit(current_user.username, 'Change Password', username)
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/audit', methods=['GET'])
@login_required
def api_admin_get_audit():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if os.path.exists(AUDIT_LOG_FILE):
        with open(AUDIT_LOG_FILE, 'r') as f:
            logs = json.load(f)
        return jsonify({'logs': logs[-100:]})  # Letzte 100 Einträge
    return jsonify({'logs': []})

if __name__ == '__main__':
    # Für Raspberry Pi: Lausche auf allen Interfaces
    app.run(host='0.0.0.0', port=5000, debug=False)