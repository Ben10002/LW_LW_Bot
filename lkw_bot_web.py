#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LKW-Bot & Gold-Zombie-Bot mit Web-Interface
Version 3.1 - Korrektur für Admin-Redirect und Zombie-Berechtigung
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
from datetime import datetime, timedelta
from pathlib import Path  # <-- HIER IST DER FEHLENDE IMPORT VON LETZTEM MAL
import pytz
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import logging

# Übersetzungen (Erweitert für Zombie-Bot)
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
        'admin_dashboard': 'Admin',
        'use_timer': 'Timer verwenden',
        'timer_minutes': 'Laufzeit (Minuten)',
        'timer_remaining': 'Verbleibende Zeit',
        'request_mode_change': 'Modus-Wechsel anfordern',
        'mode_change_requested': 'Modus-Wechsel angefordert',
        'maintenance_active': 'Wartungsarbeiten aktiv',
        'maintenance_message': 'Bot ist im Wartungsmodus - Bitte warten Sie',
        'maintenance_admin_info': 'Admin-Modus: Sie können weiterhin alle Funktionen nutzen',
        'zombie_dashboard': 'Gold-Zombies' # NEU
    },
    'en': {
        # ... (Englische Übersetzungen, hier zur Kürze weggelassen) ...
        'zombie_dashboard': 'Gold Zombies' # NEU
    }
}


# ================== SSH Konfiguration (Allgemeine Funktionen) ==================

def load_ssh_config(config_file):
    """Lade spezifische SSH-Konfiguration aus Datei"""
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Fehler beim Laden von {config_file}: {e}")
    
    return {
        'ssh_command': '',
        'ssh_password': '',
        'local_adb_port': None,
        'last_updated': None
    }

def save_ssh_config(config, config_file):
    """Speichere spezifische SSH-Konfiguration"""
    config['last_updated'] = datetime.now().isoformat()
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"SSH-Konfiguration gespeichert in {config_file}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Speichern von {config_file}: {e}")
        return False

def parse_ssh_command(ssh_command):
    """Extrahiere Informationen aus dem SSH-Command"""
    try:
        parts = ssh_command.split()
        local_port = None
        
        for i, part in enumerate(parts):
            if part == '-L' and i + 1 < len(parts):
                tunnel_info = parts[i + 1]
                local_port = tunnel_info.split(':')[0]
                break
        
        if not local_port:
             logger.warning("Konnte Local Port nicht aus SSH-Command extrahieren")
             return None

        return {'local_port': int(local_port)}
    except Exception as e:
        logger.error(f"Fehler beim Parsen des SSH-Commands: {e}")
        return None

# ================== Flask Setup ==================

app = Flask(__name__)
app.secret_key = 'dein-geheimer-schluessel-hier-ändern-123!@#'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ================== Logging ==================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lkw-bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================== Dateipfade & SPIEL-KONFIGURATION (V1-Logik) ==================

# LKW-Bot Dateien
LKW_TEMPLATE_FILE = 'rentier_template.png' # Name der Template-Datei
LKW_STAERKEN_FILE = 'lkw_staerken.txt'     # Datei für bereits geteilte Stärken
LKW_STATS_FILE = 'truck_stats.json'        # Datei für Statistiken (ersetzt truck_data.json)
LKW_SSH_CONFIG_FILE = 'ssh_config.json'

# Zombie-Bot Dateien
GOLD_ZOMBIE_SSH_CONFIG_FILE = 'gold_zombie_ssh_config.json'
GOLD_ZOMBIE_SCREENSHOT_DIR = "zombie_screenshots"

# Allgemeine Dateien
USERS_FILE = 'users.json'
AUDIT_LOG_FILE = 'audit_log.json'
MAINTENANCE_FILE = 'maintenance.json'
MODE_REQUESTS_FILE = 'mode_requests.json'


# Klick-Koordinaten (aus altem Skript)
COORDS_NEW = {
    'esc': (680, 70),           # ESC-Button oben rechts
    'share': (450, 1100),       # Teilen-Button
    'share_confirm1': (300, 450), # Bestätigung 1 - Weltchat
    'share_confirm2': (400, 750), # Bestätigung 2 - Weltchat
}

# Koordinaten für Allianz-Chat (aus altem Skript)
COORDS_ALLIANCE = {
    'esc': (680, 70),           # ESC-Button (gleich)
    'share': (450, 1100),       # Teilen-Button (gleich)
    'share_confirm1': (300, 700), # Bestätigung 1 - Allianz-Chat
    'share_confirm2': (400, 750), # Bestätigung 2 - Allianz-Chat (gleich)
}

# OCR-Boxen (aus altem Skript)
STAERKE_BOX = (200, 950, 300, 1000)   # Stärke-Bereich (links, oben, rechts, unten)
SERVER_BOX = (160, 860, 220, 915)    # Server-Bereich (links, oben, rechts, unten)


# ================== User System (Erweitert) ==================

class User(UserMixin):
    def __init__(self, username, password, role='user', blocked=False, 
                 can_choose_share_mode=True, forced_share_mode=None, 
                 can_use_zombie_bot=False): # NEUES FELD
        self.id = username
        self.username = username
        self.password = password
        self.role = role
        self.blocked = blocked
        self.can_choose_share_mode = can_choose_share_mode
        self.forced_share_mode = forced_share_mode
        self.can_use_zombie_bot = can_use_zombie_bot # NEU

def init_users():
    """Initialisiere Benutzer-Datenbank"""
    if not os.path.exists(USERS_FILE):
        users = {
            'admin': {
                'password': generate_password_hash('rREq8/1F4m#'),
                'role': 'admin',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None,
                'can_use_zombie_bot': True # NEU
            },
            'All4One': {
                'password': generate_password_hash('52B1z_'),
                'role': 'user',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None,
                'can_use_zombie_bot': False # NEU
            },
            'Server39': {
                'password': generate_password_hash('!3Z4d5'),
                'role': 'user',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None,
                'can_use_zombie_bot': False # NEU
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
    # ... (Keine Änderungen hier)
    if not os.path.exists(AUDIT_LOG_FILE):
        logs = []
    else:
        with open(AUDIT_LOG_FILE, 'r') as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    
    from datetime import datetime
    import pytz
    
    tz = pytz.timezone('Europe/Berlin')
    timestamp = datetime.now(tz).strftime('%d.%m.%Y %H:%M:%S')
    
    logs.append({
        'username': username,
        'action': action,
        'details': details,
        'timestamp': timestamp
    })
    
    logs = logs[-500:]
    
    with open(AUDIT_LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

# =========================================================================
# === HIER IST FIX #2: load_user() ===
# =========================================================================
@login_manager.user_loader
def load_user(username):
    users = load_users()
    if username in users:
        user_data = users[username]
        
        # KORREKTUR: Stelle sicher, dass 'admin' IMMER Zombie-Zugriff hat,
        # auch wenn die users.json-Datei alt ist.
        has_zombie_access = user_data.get('can_use_zombie_bot', False)
        if user_data.get('role') == 'admin':
            has_zombie_access = True
            
        return User(
            username, 
            user_data['password'], 
            user_data.get('role', 'user'), 
            user_data.get('blocked', False),
            user_data.get('can_choose_share_mode', True),
            user_data.get('forced_share_mode', None),
            has_zombie_access # Verwendet die korrigierte Variable
        )
    return None

init_users()

# ================== Bot-Steuerung (LKW-Bot) ==================

class BotController:
    def __init__(self):
        self.running = False
        self.paused = False
        self.thread = None
        self.ssh_process = None
        self.status = "Gestoppt"
        self.last_action = ""
        self.lock = threading.Lock()
        self.current_user = None
        
        self.use_timer = False
        self.timer_duration_minutes = 60
        self.timer_start_time = None
        self.timer_thread = None
        
        self.use_limit = False
        self.strength_limit = 60.0
        self.use_server_filter = False
        self.server_number = "49"
        self.reset_interval = 15
        self.share_mode = "world"
        self.adb_connected = False
        
        self.mode_change_requests = self.load_mode_change_requests()
        
        self.last_success_time = time.time()
        self.error_count = 0
        self.maintenance_mode = self.load_maintenance_mode()
        
        self.ssh_config = load_ssh_config(LKW_SSH_CONFIG_FILE) # Nutzt LKW-Config
        
        self.trucks_processed = 0
        self.trucks_shared = 0
        self.trucks_skipped = 0
        
        self.no_truck_threshold = 300
    
    # ... (Alle Funktionen des LKW-BotController bleiben hier) ...
    # ... (load_mode_change_requests, save_mode_change_requests, request_mode_change, ...)
    # ... (approve_mode_change, reject_mode_change, get_remaining_time_seconds, ...)
    # ... (check_timer, load_maintenance_mode, set_maintenance_mode, ...)
    # ... (check_auto_maintenance, log_truck_stat, setup_ssh_tunnel, ...)
    # ... (close_ssh_tunnel, make_screenshot, click, swipe, ...)
    # ... (ocr_staerke, ocr_server, ist_server_passend, rentier_lkw_finden, ...)
    # ... (staerke_float_wert, load_staerken, save_staerke, reset_staerken, ...)
    # ... (bot_loop, reset_timer, start, pause, stop)

    def load_mode_change_requests(self):
        if os.path.exists(MODE_REQUESTS_FILE):
            try:
                with open(MODE_REQUESTS_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def save_mode_change_requests(self):
        with open(MODE_REQUESTS_FILE, 'w') as f:
            json.dump(self.mode_change_requests, f, indent=2)
    
    def request_mode_change(self, username, requested_mode):
        self.mode_change_requests[username] = {
            'requested_mode': requested_mode,
            'timestamp': datetime.now().isoformat(),
            'status': 'pending'
        }
        self.save_mode_change_requests()
        logger.info(f"LKW-Bot: Mode change requested by {username}: {requested_mode}")
        
    def approve_mode_change(self, username):
        if username in self.mode_change_requests:
            req = self.mode_change_requests[username]
            users = load_users()
            if username in users:
                users[username]['forced_share_mode'] = req['requested_mode']
                users[username]['can_choose_share_mode'] = True
                save_users(users)
                req['status'] = 'approved'
                self.save_mode_change_requests()
                if self.current_user == username:
                    self.share_mode = req['requested_mode']
                return True
        return False
    
    def reject_mode_change(self, username):
        if username in self.mode_change_requests:
            self.mode_change_requests[username]['status'] = 'rejected'
            self.save_mode_change_requests()
            return True
        return False
    
    def get_remaining_time_seconds(self):
        if not self.use_timer or not self.timer_start_time:
            return None
        elapsed = time.time() - self.timer_start_time
        remaining = (self.timer_duration_minutes * 60) - elapsed
        return max(0, remaining)
    
    def check_timer(self):
        while self.running and self.use_timer:
            remaining = self.get_remaining_time_seconds()
            if remaining is not None and remaining <= 0:
                logger.info("LKW-Bot: Timer abgelaufen - Bot wird gestoppt")
                self.stop()
                break
            time.sleep(1)
        
    def load_maintenance_mode(self):
        if os.path.exists(MAINTENANCE_FILE):
            try:
                with open(MAINTENANCE_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('enabled', False)
            except json.JSONDecodeError:
                return False
        return False
    
    def set_maintenance_mode(self, enabled):
        self.maintenance_mode = enabled
        with open(MAINTENANCE_FILE, 'w') as f:
            json.dump({'enabled': enabled}, f)
        logger.info(f"LKW-Bot: Maintenance Mode: {'Aktiviert' if enabled else 'Deaktiviert'}")
    
    def check_auto_maintenance(self):
        if self.maintenance_mode:
            return
        time_since_success = time.time() - self.last_success_time
        if time_since_success > self.no_truck_threshold:
            logger.warning(f"LKW-Bot: Keine LKWs seit {int(time_since_success)}s - aktiviere Maintenance-Mode")
            self.set_maintenance_mode(True)
    
    def log_truck_stat(self, strength, server):
        if not os.path.exists(LKW_STATS_FILE):
            stats = []
        else:
            try:
                with open(LKW_STATS_FILE, 'r') as f:
                    content = f.read().strip()
                    if content:
                        stats = json.loads(content)
                    else:
                        stats = []
            except (json.JSONDecodeError, ValueError):
                logger.error(f"LKW-Bot: Korrupte Stats-Datei, erstelle neue")
                stats = []
        
        tz = pytz.timezone('Europe/Berlin')
        timestamp = datetime.now(tz).isoformat()
        
        stats.append({
            'strength': strength,
            'server': server,
            'timestamp': timestamp,
            'user': self.current_user
        })
        
        cutoff = datetime.now(tz) - timedelta(days=30)
        stats = [s for s in stats if datetime.fromisoformat(s['timestamp']) > cutoff]
        
        try:
            with open(LKW_STATS_FILE, 'w') as f:
                json.dump(stats, f, indent=2)
        except Exception as e:
            logger.error(f"LKW-Bot: Fehler beim Speichern der Stats: {e}")

        self.last_success_time = time.time()
        if self.maintenance_mode:
            logger.info("LKW-Bot: LKW gefunden - deaktiviere Maintenance-Mode")
            self.set_maintenance_mode(False)
    
    def setup_ssh_tunnel(self):
        self.ssh_config = load_ssh_config(LKW_SSH_CONFIG_FILE)
        ssh_command_str = self.ssh_config.get('ssh_command')
        ssh_password = self.ssh_config.get('ssh_password')
        local_port = self.ssh_config.get('local_adb_port')

        if not ssh_command_str or not local_port:
            logger.error("LKW-Bot: SSH-Command oder Local Port fehlt in ssh_config.json")
            self.status = "SSH-Konfig fehlt"
            self.adb_connected = False
            return False
        
        self.close_ssh_tunnel()
        cmd_parts = ssh_command_str.split()
        
        if ssh_password:
            if subprocess.run(['which', 'sshpass'], capture_output=True).returncode != 0:
                logger.error("LKW-Bot: 'sshpass' ist nicht installiert!")
                self.status = "sshpass fehlt"
                self.adb_connected = False
                return False
            cmd = ['sshpass', '-p', ssh_password] + cmd_parts
        else:
            cmd = cmd_parts
        
        logger.info(f"LKW-Bot: Starte SSH-Tunnel auf Port {local_port}...")
        
        try:
            cmd = [part for part in cmd if part not in ['-Nf', '-N', '-f']]
            cmd.extend(['-N']) 
            self.ssh_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            logger.info("LKW-Bot: Warte 7 Sekunden auf SSH-Verbindungsaufbau...")
            time.sleep(7) 
            
            poll = self.ssh_process.poll()
            if poll is not None:
                stderr_output = self.ssh_process.stderr.read()
                logger.error(f"LKW-Bot: SSH-Tunnel konnte nicht gestartet werden. Fehler: {stderr_output}")
                self.status = "SSH-Fehler"
                self.adb_connected = False
                return False
            
            logger.info(f"LKW-Bot: SSH-Tunnel aktiv. Verbinde ADB mit localhost:{local_port}...")
            adb_cmd = ['adb', 'connect', f'localhost:{local_port}']
            adb_result = subprocess.run(adb_cmd, capture_output=True, text=True, timeout=10)
            
            if 'connected' in adb_result.stdout.lower() or 'already' in adb_result.stdout.lower():
                logger.info("LKW-Bot: ADB erfolgreich verbunden")
                self.adb_connected = True
                return True
            else:
                logger.warning(f"LKW-Bot: ADB-Verbindung fehlgeschlagen: {adb_result.stdout}")
                self.close_ssh_tunnel()
                self.adb_connected = False
                return False

        except Exception as e:
            logger.error(f"LKW-Bot: Fehler beim Starten des SSH-Tunnels: {e}")
            self.close_ssh_tunnel()
            self.adb_connected = False
            return False
    
    def close_ssh_tunnel(self):
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port:
                local_port = 8583 # Fallback
            
            logger.info(f"LKW-Bot: Trenne ADB von localhost:{local_port}")
            subprocess.run(['adb', 'disconnect', f'localhost:{local_port}'], timeout=5, capture_output=True)
            
            if self.ssh_process:
                logger.info("LKW-Bot: Beende SSH-Tunnel-Prozess...")
                self.ssh_process.terminate()
                self.ssh_process.wait(timeout=5)
                self.ssh_process = None
            
            logger.info(f"LKW-Bot: Kille alle verbleibenden SSH-Prozesse auf Port {local_port}")
            pkill_cmd = f"pkill -f 'ssh.*{local_port}:adb-proxy'"
            subprocess.run(pkill_cmd, shell=True, capture_output=True)

            self.adb_connected = False
            logger.info("LKW-Bot: SSH-Tunnel und ADB sauber getrennt")
        except Exception as e:
            logger.error(f"LKW-Bot: Fehler beim Schließen des Tunnels: {e}")
    
    def make_screenshot(self, filename='screen.png'):
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port:
                logger.error("LKW-Bot: ADB-Port nicht konfiguriert")
                return False
            adb_device = f'localhost:{local_port}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'screencap', '-p', f'/sdcard/{filename}'], 
                         timeout=10, capture_output=True)
            subprocess.run(['adb', '-s', adb_device, 'pull', f'/sdcard/{filename}', filename], 
                         timeout=10, capture_output=True)
            return os.path.exists(filename)
        except Exception as e:
            logger.error(f"LKW-Bot: Screenshot-Fehler: {e}")
            return False
    
    def click(self, x, y):
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port: return False
            adb_device = f'localhost:{local_port}'
            logger.info(f"LKW-Bot: Klicke auf ({x}, {y})")
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'tap', str(x), str(y)], capture_output=True, timeout=5)
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"LKW-Bot: Klick-Fehler: {e}")
            return False
    
    def swipe(self, x1, y1, x2, y2, duration=500):
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port: return False
            adb_device = f'localhost:{local_port}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'swipe', 
                          str(x1), str(y1), str(x2), str(y2), str(duration)], capture_output=True)
            return True
        except Exception as e:
            logger.error(f"LKW-Bot: Swipe-Fehler: {e}")
            return False
    
    def ocr_staerke(self):
        try:
            img = Image.open('info.png')
            staerke_img = img.crop(STAERKE_BOX)
            configs = ['--psm 7', '--psm 8', '--psm 6']
            for config in configs:
                wert = pytesseract.image_to_string(staerke_img, lang='eng', config=config).strip()
                if wert and ('m' in wert.lower() or 'M' in wert):
                    logger.info(f"LKW-Bot: OCR Stärke: {wert}")
                    return wert
            logger.warning("LKW-Bot: OCR konnte keine Stärke finden")
            return ""
        except Exception as e:
            logger.error(f"LKW-Bot: OCR-Fehler: {e}")
            return ""

    def ocr_server(self):
        try:
            img = Image.open('info.png')
            server_img = img.crop(SERVER_BOX)
            server_text = pytesseract.image_to_string(server_img, lang='eng').strip()
            logger.info(f"LKW-Bot: OCR Server: '{server_text}'")
            s_txt = re.sub(r'[^0-9]', '', server_text)
            return s_txt if s_txt else "Unknown"
        except Exception as e:
            logger.error(f"LKW-Bot: Server-OCR-Fehler: {e}")
            return "Unknown"

    def ist_server_passend(self):
        try:
            img = Image.open('info.png')
            server_img = img.crop(SERVER_BOX)
            server_text = pytesseract.image_to_string(server_img, lang='eng').strip()
            logger.info(f"LKW-Bot: OCR Server: '{server_text}'")
            s_txt = server_text.replace(' ', '').replace('O', '0')
            return (f"#{self.server_number}" in s_txt) or (self.server_number in s_txt)
        except Exception as e:
            logger.error(f"LKW-Bot: Server-Check-Fehler: {e}")
            return False

    def rentier_lkw_finden(self):
        try:
            screenshot = cv2.imread('screen.png')
            template = cv2.imread(LKW_TEMPLATE_FILE)
            if screenshot is None:
                logger.error("LKW-Bot: Screenshot-Datei 'screen.png' konnte nicht gelesen werden")
                return None
            if template is None:
                logger.error(f"LKW-Bot: Template-Datei '{LKW_TEMPLATE_FILE}' konnte nicht gelesen werden")
                return None
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= 0.40)
            matches = [(int(pt[0]), int(pt[1])) for pt in zip(*locations[::-1])]
            return matches if matches else None
        except Exception as e:
            logger.error(f"LKW-Bot: Template-Matching-Fehler: {e}")
            return None

    def staerke_float_wert(self, staerke_text):
        match = re.search(r"([\d\.,]+)\s*[mM]", staerke_text)
        if match:
            try:
                zahl_str = match.group(1).replace(',', '.')
                zahl = float(zahl_str)
                if zahl >= 100 and '.' not in match.group(1) and ',' not in match.group(1):
                    zahl = zahl / 10
                    logger.info(f"LKW-Bot: Komma-Korrektur: {match.group(1)}M → {zahl}M")
                return zahl
            except ValueError:
                return None
        return None

    def load_staerken(self):
        if os.path.exists(LKW_STAERKEN_FILE):
            try:
                with open(LKW_STAERKEN_FILE, 'r', encoding="utf-8") as f:
                    return f.read().splitlines()
            except Exception as e:
                logger.error(f"LKW-Bot: Fehler beim Laden der Stärken: {e}")
                return []
        return []
    
    def save_staerke(self, staerke):
        try:
            with open(LKW_STAERKEN_FILE, "a", encoding="utf-8") as f:
                f.write(staerke + "\n")
            logger.info(f"LKW-Bot: Stärke {staerke} notiert")
        except Exception as e:
            logger.error(f"LKW-Bot: Fehler beim Notieren der Stärke: {e}")
    
    def reset_staerken(self):
        try:
            with open(LKW_STAERKEN_FILE, "w", encoding="utf-8") as f:
                f.write("")
            logger.info("LKW-Bot: Stärken-Liste zurückgesetzt")
        except Exception as e:
            logger.error(f"LKW-Bot: Reset-Fehler: {e}")

    def bot_loop(self):
        logger.info("LKW-Bot: Bot-Schleife gestartet")
        if not self.setup_ssh_tunnel():
            self.status = "Fehler: SSH-Tunnel konnte nicht aufgebaut werden"
            self.running = False
            return
        
        reset_thread = threading.Thread(target=self.reset_timer, daemon=True)
        reset_thread.start()
        
        if self.use_timer:
            self.timer_start_time = time.time()
            self.timer_thread = threading.Thread(target=self.check_timer, daemon=True)
            self.timer_thread.start()
            logger.info(f"LKW-Bot: Auto-Stop Timer gestartet für {self.timer_duration_minutes} Minuten")
        
        while self.running:
            if self.paused:
                self.status = "Pausiert"
                time.sleep(1)
                continue
            
            if self.maintenance_mode:
                self.status = "Maintenance-Mode"
                self.last_action = "Wartungsarbeiten - Bot pausiert"
                time.sleep(10)
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
                logger.info(f"LKW-Bot: Treffer bei: {treffer[0]}")
                
                lx = treffer[0][0] + 5
                ly = treffer[0][1] + 5
                self.click(lx, ly)
                
                if not self.make_screenshot('info.png'):
                    self.last_action = "Fehler: Info-Screenshot fehlgeschlagen"
                    continue
                
                if self.use_server_filter:
                    self.last_action = "Prüfe Server..."
                    if not self.ist_server_passend():
                        self.last_action = f"Falscher Server - ESC"
                        self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1])
                        self.trucks_skipped += 1
                        self.trucks_processed += 1
                        continue
                
                self.last_action = "Lese Stärke..."
                staerke = self.ocr_staerke()
                wert = self.staerke_float_wert(staerke)
                logger.info(f"LKW-Bot: Stärke gelesen: '{staerke}' Wert: {wert}")
                
                limit_passed = True
                if self.use_limit and wert is not None:
                    if wert > self.strength_limit:
                        limit_passed = False
                        self.last_action = f"Stärke {wert} > {self.strength_limit} - übersprungen"
                
                if wert is None or not limit_passed or (staerke in self.load_staerken()):
                    if wert is None:
                        self.last_action = "Keine Stärke erkannt - Lade Liste neu"
                        self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1])
                        time.sleep(0.5)
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
                
                self.last_action = f"Teile LKW (Stärke: {staerke})"
                self.save_staerke(staerke)
                server = self.ocr_server()
                
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
                
                self.log_truck_stat(staerke, server)
                
            except Exception as e:
                logger.error(f"LKW-Bot: Fehler in Bot-Schleife: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.last_action = f"Fehler: {str(e)}"
                time.sleep(5)
            
            self.check_auto_maintenance()
        
        self.close_ssh_tunnel()
        self.status = "Gestoppt"
        logger.info("LKW-Bot: Bot-Schleife beendet")
    
    def reset_timer(self):
        while self.running:
            time.sleep(self.reset_interval * 60)
            if self.running:
                self.reset_staerken()
                self.last_action = f"Stärken-Liste nach {self.reset_interval} Min. zurückgesetzt"
    
    def start(self):
        if not self.running:
            self.running = True
            self.paused = False
            self.thread = threading.Thread(target=self.bot_loop, daemon=True)
            self.thread.start()
            logger.info(f"LKW-Bot: Gestartet von {self.current_user}")
    
    def pause(self):
        if self.running:
            self.paused = not self.paused
            logger.info(f"LKW-Bot: {'Pausiert' if self.paused else 'Fortgesetzt'}")
    
    def stop(self):
        self.running = False
        self.use_timer = False
        self.timer_start_time = None
        if self.thread:
            self.thread.join(timeout=10)
        if self.timer_thread:
            self.timer_thread.join(timeout=5)
        logger.info("LKW-Bot: Gestoppt")


# Globale Instanz LKW-Bot
bot = BotController()


# ================== Bot-Steuerung (Gold-Zombie-Bot) ==================

class GoldZombieController:
    
    # Koordinaten aus altem Skript
    CLICK_1 = (780, 300)
    CLICK_2 = (200, 1500)
    CLICK_3 = (500, 1200)
    TRUPP_1 = (200, 1400)
    TRUPP_2 = (400, 1400)
    TRUPP_3 = (600, 1400)
    BESTAETIGEN = (450, 1200)
    AUSDAUER_50 = (700, 1000)
    AUSDAUER_10 = (700, 800)
    AUSDAUER_SCHLIESSEN = (800, 200)
    TIMER_REGION = (250, 1150, 650, 1300) # (x1, y1, x2, y2)

    class TruppTimer:
        """Interne Klasse zur Verwaltung von Trupp-Cooldowns"""
        def __init__(self, trupp_nummer):
            self.trupp_nummer = trupp_nummer
            self.verfuegbar_ab = None
            self.letzte_cooldown_sekunden = 0
        
        def set_timer(self, stunden, minuten, sekunden):
            dauer = timedelta(hours=stunden, minutes=minuten, seconds=sekunden)
            self.verfuegbar_ab = datetime.now() + dauer
            self.letzte_cooldown_sekunden = stunden * 3600 + minuten * 60 + sekunden
            logger.info(f"Zombie-Bot: Trupp {self.trupp_nummer} Timer: {stunden:02d}:{minuten:02d}:{sekunden:02d}")
        
        def ist_verfuegbar(self):
            if self.verfuegbar_ab is None:
                return True
            return datetime.now() >= self.verfuegbar_ab
        
        def zeit_bis_verfuegbar(self):
            if self.ist_verfuegbar():
                return 0
            return (self.verfuegbar_ab - datetime.now()).total_seconds()
        
        def get_letzte_cooldown_sekunden(self):
            return self.letzte_cooldown_sekunden

    def __init__(self):
        self.running = False
        self.paused = False
        self.thread = None
        self.ssh_process = None
        self.status = "Gestoppt"
        self.lock = threading.Lock()
        
        # Zeit- und Zählerstatus
        self.start_time = None
        self.ausdauer_50_verwendet = 0
        self.ausdauer_10_verwendet = 0
        self.truppen_deployed = 0
        
        # Einstellungen
        self.ausdauer_50_limit = 0
        self.ausdauer_10_limit = 0
        self.unbegrenzt_mode = False
        self.use_trupp_1 = False
        self.use_trupp_2 = True
        self.use_trupp_3 = True
        
        # SSH & ADB
        self.adb_connected = False
        self.ssh_config = load_ssh_config(GOLD_ZOMBIE_SSH_CONFIG_FILE) # EIGENE Config-Datei

        # Screenshot-Ordner erstellen
        Path(GOLD_ZOMBIE_SCREENSHOT_DIR).mkdir(exist_ok=True)

    # --- SSH- und ADB-Funktionen (Kopiert von LKW-Bot, angepasst) ---
    
    def setup_ssh_tunnel(self):
        """Erstellt SSH-Tunnel für den Zombie-Bot"""
        self.ssh_config = load_ssh_config(GOLD_ZOMBIE_SSH_CONFIG_FILE)
        ssh_command_str = self.ssh_config.get('ssh_command')
        ssh_password = self.ssh_config.get('ssh_password')
        local_port = self.ssh_config.get('local_adb_port')

        if not ssh_command_str or not local_port:
            logger.error("Zombie-Bot: SSH-Command oder Local Port fehlt in Config")
            self.status = "SSH-Konfig fehlt"
            self.adb_connected = False
            return False
        
        self.close_ssh_tunnel()
        cmd_parts = ssh_command_str.split()
        
        if ssh_password:
            if subprocess.run(['which', 'sshpass'], capture_output=True).returncode != 0:
                logger.error("Zombie-Bot: 'sshpass' ist nicht installiert!")
                self.status = "sshpass fehlt"
                self.adb_connected = False
                return False
            cmd = ['sshpass', '-p', ssh_password] + cmd_parts
        else:
            cmd = cmd_parts
        
        logger.info(f"Zombie-Bot: Starte SSH-Tunnel auf Port {local_port}...")
        
        try:
            cmd = [part for part in cmd if part not in ['-Nf', '-N', '-f']]
            cmd.extend(['-N']) 
            self.ssh_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            logger.info("Zombie-Bot: Warte 7 Sekunden auf SSH-Verbindungsaufbau...")
            time.sleep(7) 
            
            poll = self.ssh_process.poll()
            if poll is not None:
                stderr_output = self.ssh_process.stderr.read()
                logger.error(f"Zombie-Bot: SSH-Tunnel konnte nicht gestartet werden. Fehler: {stderr_output}")
                self.status = "SSH-Fehler"
                self.adb_connected = False
                return False
            
            logger.info(f"Zombie-Bot: SSH-Tunnel aktiv. Verbinde ADB mit localhost:{local_port}...")
            adb_cmd = ['adb', 'connect', f'localhost:{local_port}']
            adb_result = subprocess.run(adb_cmd, capture_output=True, text=True, timeout=10)
            
            if 'connected' in adb_result.stdout.lower() or 'already' in adb_result.stdout.lower():
                logger.info("Zombie-Bot: ADB erfolgreich verbunden")
                self.adb_connected = True
                return True
            else:
                logger.warning(f"Zombie-Bot: ADB-Verbindung fehlgeschlagen: {adb_result.stdout}")
                self.close_ssh_tunnel()
                self.adb_connected = False
                return False

        except Exception as e:
            logger.error(f"Zombie-Bot: Fehler beim Starten des SSH-Tunnels: {e}")
            self.close_ssh_tunnel()
            self.adb_connected = False
            return False

    def close_ssh_tunnel(self):
        """Schließt SSH-Tunnel für den Zombie-Bot"""
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port:
                local_port = 8676 # Fallback
            
            logger.info(f"Zombie-Bot: Trenne ADB von localhost:{local_port}")
            subprocess.run(['adb', 'disconnect', f'localhost:{local_port}'], timeout=5, capture_output=True)
            
            if self.ssh_process:
                logger.info("Zombie-Bot: Beende SSH-Tunnel-Prozess...")
                self.ssh_process.terminate()
                self.ssh_process.wait(timeout=5)
                self.ssh_process = None
            
            logger.info(f"Zombie-Bot: Kille alle verbleibenden SSH-Prozesse auf Port {local_port}")
            pkill_cmd = f"pkill -f 'ssh.*{local_port}:adb-proxy'"
            subprocess.run(pkill_cmd, shell=True, capture_output=True)

            self.adb_connected = False
            logger.info("Zombie-Bot: SSH-Tunnel und ADB sauber getrennt")
        except Exception as e:
            logger.error(f"Zombie-Bot: Fehler beim Schließen des Tunnels: {e}")

    def tap(self, x, y):
        """Simuliert einen Tap für den Zombie-Bot"""
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port: return False
            adb_device = f'localhost:{local_port}'
            logger.info(f"Zombie-Bot: Klicke auf ({x}, {y})")
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'tap', str(x), str(y)], capture_output=True, timeout=5)
            time.sleep(2) # Original-Sleep
            return True
        except Exception as e:
            logger.error(f"Zombie-Bot: Klick-Fehler: {e}")
            return False

    def take_screenshot(self, filename="screenshot.png"):
        """Macht einen Screenshot für den Zombie-Bot"""
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port: return False
            adb_device = f'localhost:{local_port}'

            screenshot_path = Path(GOLD_ZOMBIE_SCREENSHOT_DIR) / filename
            
            subprocess.run(['adb', '-s', adb_device, 'shell', 'screencap', '-p', f'/sdcard/{filename}'], 
                         timeout=10, capture_output=True)
            
            pull_command = f'adb -s {adb_device} pull /sdcard/{filename} "{screenshot_path}"'
            result = subprocess.run(pull_command, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Zombie-Bot: Fehler beim Herunterladen des Screenshots: {result.stderr}")
                return None
            
            if not screenshot_path.exists():
                logger.error(f"Zombie-Bot: Screenshot wurde nicht erstellt: {screenshot_path}")
                return None
            
            logger.info(f"Zombie-Bot: Screenshot gespeichert: {screenshot_path}")
            return screenshot_path
        except Exception as e:
            logger.error(f"Zombie-Bot: Screenshot-Fehler: {e}")
            return None

    # --- Spiel-Logik-Funktionen (aus altem Skript) ---
    
    def pruefe_ausdauer_erhalten(self):
        """Prüft ob "Ausdauer erhalten" im Timer-Bereich angezeigt wird"""
        try:
            screenshot_path = self.take_screenshot("ausdauer_check.png")
            if screenshot_path is None:
                return False
            
            img = Image.open(screenshot_path)
            x1, y1, x2, y2 = self.TIMER_REGION
            cropped = img.crop((x1, y1, x2, y2))
            cropped_gray = cropped.convert('L')
            
            text = pytesseract.image_to_string(cropped_gray, config='--psm 6')
            text_clean = text.replace('\n', ' ').replace(' ', '').lower()
            
            logger.info(f"Zombie-Bot: Suche nach 'Ausdauer erhalten': '{text.strip()}'")
            
            if 'ausdauer' in text_clean and 'erhalten' in text_clean:
                logger.info(f"Zombie-Bot: 'Ausdauer erhalten' gefunden!")
                return True
            else:
                logger.info(f"Zombie-Bot: 'Ausdauer erhalten' nicht gefunden")
                return False
                
        except Exception as e:
            logger.error(f"Zombie-Bot: Fehler bei Ausdauer-Prüfung: {e}")
            return False

    def sammle_ausdauer(self):
        """Sammelt Ausdauer wenn verfügbar"""
        logger.info("Zombie-Bot: Sammle Ausdauer...")
        
        self.tap(*self.BESTAETIGEN)
        time.sleep(1)
        
        ausdauer_gesammelt = False
        
        if self.unbegrenzt_mode or self.ausdauer_50_verwendet < self.ausdauer_50_limit:
            logger.info(f"Zombie-Bot: Klicke auf 50 Ausdauer ({self.ausdauer_50_verwendet + 1}/{self.ausdauer_50_limit if not self.unbegrenzt_mode else '∞'})")
            self.tap(*self.AUSDAUER_50)
            self.ausdauer_50_verwendet += 1
            ausdauer_gesammelt = True
            time.sleep(1)
        
        if self.unbegrenzt_mode or self.ausdauer_10_verwendet < self.ausdauer_10_limit:
            logger.info(f"Zombie-Bot: Klicke auf 10 Ausdauer ({self.ausdauer_10_verwendet + 1}/{self.ausdauer_10_limit if not self.unbegrenzt_mode else '∞'})")
            self.tap(*self.AUSDAUER_10)
            self.ausdauer_10_verwendet += 1
            ausdauer_gesammelt = True
            time.sleep(1)
        
        logger.info("Zombie-Bot: Schließe Ausdauer-Fenster")
        self.tap(*self.AUSDAUER_SCHLIESSEN)
        time.sleep(1)
        
        logger.info("Zombie-Bot: Klicke auf Bestätigen nach Ausdauer sammeln...")
        self.tap(*self.BESTAETIGEN)
        time.sleep(1)
        
        if not ausdauer_gesammelt:
            logger.warning("Zombie-Bot: Ausdauer-Limit erreicht!")
            
        return ausdauer_gesammelt

    def extract_timer_from_region(self):
        """Extrahiert die Timer-Zeit aus dem definierten Bereich"""
        try:
            screenshot_path = self.take_screenshot("timer_check.png")
            if screenshot_path is None:
                return None
            
            img = Image.open(screenshot_path)
            x1, y1, x2, y2 = self.TIMER_REGION
            cropped = img.crop((x1, y1, x2, y2))
            
            cropped_gray = cropped.convert('L')
            
            text = pytesseract.image_to_string(cropped_gray, config='--psm 6')
            logger.info(f"Zombie-Bot: OCR Text: '{text.strip()}'")
            
            pattern = r'(\d{1,2}):(\d{2}):(\d{2})'
            match = re.search(pattern, text)
            
            if match:
                stunden = int(match.group(1))
                minuten = int(match.group(2))
                sekunden = int(match.group(3))
                logger.info(f"Zombie-Bot: Zeit erkannt: {stunden:02d}:{minuten:02d}:{sekunden:02d}")
                return (stunden, minuten, sekunden)
            else:
                logger.warning(f"Zombie-Bot: Keine Zeit im Format xx:xx:xx gefunden")
                return None
                
        except Exception as e:
            logger.error(f"Zombie-Bot: Fehler bei OCR: {e}")
            return None

    def schritte_1_bis_3(self):
        """Führt die Schritte 1-3 aus"""
        if not self.running: return
        logger.info("Zombie-Bot: Führe Schritte 1-3 aus...")
        
        self.tap(*self.CLICK_1)
        if not self.running: return
        time.sleep(1)
        self.tap(*self.CLICK_2)
        if not self.running: return
        time.sleep(3)
        self.tap(*self.CLICK_3)
        time.sleep(1)

    def waehle_trupp_und_setze_timer(self, trupp_position, trupp_timer):
        """Wählt eine Truppe aus und setzt deren Timer"""
        if not self.running: return "gestoppt"
        
        logger.info(f"Zombie-Bot: Wähle Trupp {trupp_timer.trupp_nummer}...")
        self.tap(*trupp_position)
        time.sleep(1)
        
        if not self.running: return "gestoppt"
        
        if self.pruefe_ausdauer_erhalten():
            if not self.unbegrenzt_mode and self.ausdauer_50_verwendet >= self.ausdauer_50_limit and self.ausdauer_10_verwendet >= self.ausdauer_10_limit:
                logger.info("Zombie-Bot: ALLE AUSDAUER-LIMITS ERREICHT - SKRIPT WIRD BEENDET!")
                self.running = False
                return "limit_erreicht"
            
            ausdauer_gesammelt = self.sammle_ausdauer()
            if not self.running: return "gestoppt"
            
            if not ausdauer_gesammelt:
                logger.info("Zombie-Bot: AUSDAUER-LIMIT ERREICHT - SKRIPT WIRD BEENDET!")
                self.running = False
                return "limit_erreicht"
            
            timer_daten = self.extract_timer_from_region()
            if timer_daten:
                trupp_timer.set_timer(*timer_daten)
            else:
                logger.warning(f"Zombie-Bot: Konnte Timer für Trupp {trupp_timer.trupp_nummer} nicht lesen! Setze 1 Min Fallback.")
                trupp_timer.set_timer(0, 1, 0)
            
            self.truppen_deployed += 1
            logger.info(f"Zombie-Bot: 🚀 Truppe #{self.truppen_deployed} losgeschickt!")
            return "timer_gesetzt"
        
        if not self.running: return "gestoppt"

        timer_daten = self.extract_timer_from_region()
        if timer_daten:
            trupp_timer.set_timer(*timer_daten)
        else:
            logger.warning(f"Zombie-Bot: Konnte Timer für Trupp {trupp_timer.trupp_nummer} nicht lesen! Setze 1 Min Fallback.")
            trupp_timer.set_timer(0, 1, 0)
        
        if not self.running: return "gestoppt"
        
        time.sleep(0.5)
        logger.info("Zombie-Bot: Klicke auf Bestätigen...")
        self.tap(*self.BESTAETIGEN)
        time.sleep(1)
        
        self.truppen_deployed += 1
        logger.info(f"Zombie-Bot: 🚀 Truppe #{self.truppen_deployed} losgeschickt!")
        return "timer_gesetzt"

    # --- Haupt-Loop und Steuerung ---

    def bot_loop(self):
        """Hauptprogramm - Automatisierungs-Loop"""
        logger.info("=" * 60)
        logger.info("🧟 GOLD-ZOMBIE-BOT GESTARTET")
        logger.info("=" * 60)
        
        if not self.setup_ssh_tunnel():
            self.status = "Fehler: SSH-Tunnel konnte nicht aufgebaut werden"
            self.running = False
            return
        
        self.start_time = datetime.now()
        
        # Zähler zurücksetzen
        self.ausdauer_50_verwendet = 0
        self.ausdauer_10_verwendet = 0
        self.truppen_deployed = 0
        
        trupp_timers = {}
        trupp_positions = {}
        
        if self.use_trupp_1:
            trupp_timers[1] = self.TruppTimer(1)
            trupp_positions[1] = self.TRUPP_1
        if self.use_trupp_2:
            trupp_timers[2] = self.TruppTimer(2)
            trupp_positions[2] = self.TRUPP_2
        if self.use_trupp_3:
            trupp_timers[3] = self.TruppTimer(3)
            trupp_positions[3] = self.TRUPP_3

        logger.info("Zombie-Bot: Starte initiale Sequenz...")
        
        for trupp_num in sorted(trupp_timers.keys()):
            self.schritte_1_bis_3()
            result = self.waehle_trupp_und_setze_timer(trupp_positions[trupp_num], trupp_timers[trupp_num])
            if result == "limit_erreicht":
                self.stop()
                return
            if not self.running:
                return
        
        logger.info("=" * 60)
        logger.info("Zombie-Bot: 🔄 ENDLOSSCHLEIFE GESTARTET")
        logger.info("=" * 60)
        
        durchlauf = 0
        while self.running:
            durchlauf += 1
            self.status = f"Läuft (Durchlauf #{durchlauf})"
            logger.info(f"\nZombie-Bot: Durchlauf #{durchlauf}")
            
            if self.paused:
                self.status = "Pausiert"
                logger.info("Zombie-Bot: Pausiert...")
                while self.paused and self.running:
                    time.sleep(1)
                if not self.running:
                    break
            
            self.schritte_1_bis_3()
            if not self.running: break
            
            verfuegbare_truppen = []
            for trupp_num, timer in trupp_timers.items():
                if timer.ist_verfuegbar():
                    verfuegbare_truppen.append(trupp_num)
            
            logger.info("Zombie-Bot: Status:")
            for trupp_num, timer in sorted(trupp_timers.items()):
                status = '✅ Verfügbar' if timer.ist_verfuegbar() else f'❌ Noch {timer.zeit_bis_verfuegbar():.0f}s'
                logger.info(f"  Trupp {trupp_num}: {status}")
            
            if not self.running: break
            
            if verfuegbare_truppen:
                if len(verfuegbare_truppen) > 1:
                    beste_trupp = min(verfuegbare_truppen, key=lambda t: trupp_timers[t].get_letzte_cooldown_sekunden())
                    logger.info(f"Zombie-Bot: Wähle Trupp {beste_trupp} (kürzester Cooldown)")
                else:
                    beste_trupp = verfuegbare_truppen[0]
                
                result = self.waehle_trupp_und_setze_timer(trupp_positions[beste_trupp], trupp_timers[beste_trupp])
                
                if result in ["limit_erreicht", "gestoppt"]:
                    break
            else:
                naechste_trupp = min(trupp_timers.items(), key=lambda x: x[1].zeit_bis_verfuegbar())
                trupp_num, timer = naechste_trupp
                warte_zeit = timer.zeit_bis_verfuegbar()
                
                logger.info(f"Zombie-Bot: ⏳ Warte {warte_zeit:.0f}s auf Trupp {trupp_num}...")
                self.status = f"Warte auf Trupp {trupp_num} ({warte_zeit:.0f}s)"
                
                wait_steps = int(warte_zeit * 2) + 2
                for _ in range(wait_steps):
                    if not self.running: break
                    time.sleep(0.5)
                
                if not self.running: break
                
                result = self.waehle_trupp_und_setze_timer(trupp_positions[trupp_num], trupp_timers[trupp_num])
                if result in ["limit_erreicht", "gestoppt"]:
                    break
            
            if not self.running: break
            
            for _ in range(4):
                if not self.running: break
                time.sleep(0.5)
        
        self.close_ssh_tunnel()
        self.status = "Gestoppt"
        logger.info("=" * 60)
        logger.info("🛑 ZOMBIE-BOT BEENDET")
        logger.info("=" * 60)

    def start(self):
        """Startet den Zombie-Bot"""
        with self.lock:
            if not self.running:
                self.running = True
                self.paused = False
                self.thread = threading.Thread(target=self.bot_loop, daemon=True)
                self.thread.start()
                logger.info("Zombie-Bot: Gestartet")
    
    def pause(self):
        """Pausiert/Fortsetzt den Zombie-Bot"""
        if self.running:
            self.paused = not self.paused
            self.status = "Pausiert" if self.paused else "Läuft"
            logger.info(f"Zombie-Bot: {'Pausiert' if self.paused else 'Fortgesetzt'}")
    
    def stop(self):
        """Stoppt den Zombie-Bot"""
        with self.lock:
            self.running = False
            self.paused = False
            if self.thread:
                self.thread.join(timeout=5)
            self.status = "Gestoppt"
            logger.info("Zombie-Bot: Gestoppt")


# Globale Instanz Zombie-Bot
zombie_bot = GoldZombieController()


# ================== Flask Routes (LKW-Bot) ==================

def get_language():
    return session.get('language', 'de')

def translate(key):
    lang = get_language()
    return TRANSLATIONS.get(lang, TRANSLATIONS['de']).get(key, key)

@app.route('/set_language/<lang>')
def set_language(lang):
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
                user = load_user(username) # Nutze user_loader für volles User-Objekt
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

# =========================================================================
# === HIER IST FIX #1: index() Route ===
# =========================================================================
@app.route('/')
@login_required
def index():
    # KORREKTUR: Zeigt IMMER das LKW-Bot Dashboard (index.html).
    # Das Admin-Panel ist separat unter /admin erreichbar.
    return render_template('index.html', t=translate, lang=get_language(), user=current_user)

@app.route('/api/status')
@login_required
def api_status():
    remaining_time = None
    if bot.use_timer:
        remaining_seconds = bot.get_remaining_time_seconds()
        if remaining_seconds is not None:
            minutes = int(remaining_seconds // 60)
            seconds = int(remaining_seconds % 60)
            remaining_time = f"{minutes:02d}:{seconds:02d}"
    
    return jsonify({
        'running': bot.running,
        'paused': bot.paused,
        'status': bot.status,
        'last_action': bot.last_action,
        'trucks_processed': bot.trucks_processed,
        'trucks_shared': bot.trucks_shared,
        'trucks_skipped': bot.trucks_skipped,
        'adb_connected': bot.adb_connected,
        'current_user': bot.current_user,
        'maintenance_mode': bot.maintenance_mode,
        'timer_remaining': remaining_time,
        'use_timer': bot.use_timer
    })

@app.route('/api/start', methods=['POST'])
@login_required
def api_start():
    users = load_users()
    if current_user.username in users and users[current_user.username].get('blocked', False):
        return jsonify({'error': 'User is blocked'}), 403
    
    with bot.lock:
        if bot.current_user and bot.current_user != current_user.username:
            if current_user.role != 'admin':
                return jsonify({'error': f'Bot wird bereits von {bot.current_user} verwendet'}), 409
            bot.stop()
        
        bot.current_user = current_user.username
        bot.start()
        log_audit(current_user.username, 'Start LKW-Bot', f'Timer: {bot.use_timer}, Duration: {bot.timer_duration_minutes}min')
    
    return jsonify({'success': True})

@app.route('/api/pause', methods=['POST'])
@login_required
def api_pause():
    bot.pause()
    log_audit(current_user.username, 'Pause LKW-Bot', '')
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    with bot.lock:
        bot.stop()
        bot.current_user = None
        log_audit(current_user.username, 'Stop LKW-Bot', '')
    return jsonify({'success': True})

@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def api_settings():
    if request.method == 'POST':
        users = load_users()
        if current_user.username in users and users[current_user.username].get('blocked', False):
            return jsonify({'error': 'User is blocked'}), 403
        
        data = request.json
        bot.use_limit = data.get('use_limit', False)
        bot.strength_limit = float(data.get('strength_limit', 60))
        bot.use_server_filter = data.get('use_server_filter', False)
        bot.server_number = data.get('server_number', '49')
        bot.reset_interval = int(data.get('reset_interval', 15))
        
        bot.use_timer = data.get('use_timer', False)
        bot.timer_duration_minutes = int(data.get('timer_duration', 60))
        
        user_data = users.get(current_user.username, {})
        if user_data.get('can_choose_share_mode', True):
            bot.share_mode = data.get('share_mode', 'world')
        else:
            bot.share_mode = user_data.get('forced_share_mode', 'world')
        
        log_audit(current_user.username, 'Change LKW-Bot Settings', f"limit={data.get('use_limit')}, mode={bot.share_mode}")
        return jsonify({'success': True})
    else:
        users = load_users()
        user_data = users.get(current_user.username, {})
        can_choose = user_data.get('can_choose_share_mode', True)
        forced_mode = user_data.get('forced_share_mode', None)
        mode_request = bot.mode_change_requests.get(current_user.username, {})
        
        return jsonify({
            'use_limit': bot.use_limit,
            'strength_limit': bot.strength_limit,
            'use_server_filter': bot.use_server_filter,
            'server_number': bot.server_number,
            'reset_interval': bot.reset_interval,
            'share_mode': forced_mode if forced_mode and not can_choose else bot.share_mode,
            'can_choose_share_mode': can_choose,
            'forced_share_mode': forced_mode,
            'use_timer': bot.use_timer,
            'timer_duration': bot.timer_duration_minutes,
            'mode_change_request': mode_request.get('status', None),
            'requested_mode': mode_request.get('requested_mode', None)
        })

@app.route('/api/request_mode_change', methods=['POST'])
@login_required
def api_request_mode_change():
    data = request.json
    requested_mode = data.get('requested_mode')
    if requested_mode in ['world', 'alliance']:
        bot.request_mode_change(current_user.username, requested_mode)
        log_audit(current_user.username, 'Request Mode Change', requested_mode)
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid mode'}), 400

@app.route('/api/reset_stats', methods=['POST'])
@login_required
def api_reset_stats():
    bot.trucks_processed = 0
    bot.trucks_shared = 0
    bot.trucks_skipped = 0
    log_audit(current_user.username, 'Reset LKW-Bot Statistics', '')
    return jsonify({'success': True})

# ================== Admin Routes (Erweitert) ==================

@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html', user=current_user)

@app.route('/api/admin/ssh_config', methods=['GET', 'POST'])
@login_required
def api_admin_ssh_config():
    """ Verwaltet die LKW-Bot SSH-Config """
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'POST':
        data = request.json
        ssh_command = data.get('ssh_command', '').strip()
        ssh_password = data.get('ssh_password', '').strip()
        if not ssh_command:
            return jsonify({'error': 'SSH-Command ist erforderlich'}), 400
        
        parsed = parse_ssh_command(ssh_command)
        if not parsed:
            return jsonify({'error': 'Ungültiger SSH-Command'}), 400
        
        config = {
            'ssh_command': ssh_command,
            'ssh_password': ssh_password,
            'local_adb_port': parsed.get('local_port')
        }
        
        if save_ssh_config(config, LKW_SSH_CONFIG_FILE):
            bot.ssh_config = config
            if bot.running:
                logger.info("LKW-Bot läuft, starte SSH-Tunnel neu...")
                bot.close_ssh_tunnel()
                time.sleep(1)
                bot.setup_ssh_tunnel()
            log_audit(current_user.username, 'Update LKW-Bot SSH Config')
            return jsonify({'success': True, 'message': 'SSH-Konfiguration gespeichert'})
        else:
            return jsonify({'error': 'Fehler beim Speichern'}), 500
    else:
        config = load_ssh_config(LKW_SSH_CONFIG_FILE)
        return jsonify({
            'ssh_command': config.get('ssh_command', ''),
            'ssh_password': config.get('ssh_password', ''),
            'local_adb_port': config.get('local_adb_port'),
            'last_updated': config.get('last_updated', None)
        })

@app.route('/api/admin/test_ssh', methods=['POST'])
@login_required
def api_admin_test_ssh():
    """ Testet die LKW-Bot SSH-Config """
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        bot.close_ssh_tunnel()
        time.sleep(1)
        if bot.setup_ssh_tunnel():
            return jsonify({'success': True, 'message': 'LKW-Bot SSH-Tunnel und ADB erfolgreich verbunden'})
        else:
            return jsonify({'success': False, 'message': 'LKW-Bot Verbindung fehlgeschlagen - Bitte Logs prüfen'}), 400
    except Exception as e:
        logger.error(f"LKW-Bot Fehler beim Testen der SSH-Verbindung: {e}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

@app.route('/api/admin/users')
@login_required
def api_admin_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    user_list = []
    for username, data in users.items():
        # Lade den Benutzer mit der korrigierten Logik, um sicherzustellen, dass Admin Rechte hat
        user_obj = load_user(username)
        user_list.append({
            'username': username,
            'role': data['role'],
            'blocked': data.get('blocked', False),
            'can_choose_share_mode': data.get('can_choose_share_mode', True),
            'forced_share_mode': data.get('forced_share_mode', None),
            'can_use_zombie_bot': user_obj.can_use_zombie_bot # Benutze den geladenen Wert
        })
    return jsonify({'users': user_list})

@app.route('/api/admin/user/toggle_block/<username>', methods=['POST'])
@login_required
def api_admin_toggle_block(username):
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    if username in users:
        users[username]['blocked'] = not users[username].get('blocked', False)
        save_users(users)
        log_audit(current_user.username, 'Toggle User Block', username)
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/user/set_share_mode/<username>', methods=['POST'])
@login_required
def api_admin_set_share_mode(username):
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    data = request.json
    users = load_users()
    if username in users:
        users[username]['can_choose_share_mode'] = data.get('can_choose', True)
        users[username]['forced_share_mode'] = data.get('forced_mode', None)
        save_users(users)
        log_audit(current_user.username, 'Set User Share Mode', f"{username}: {data}")
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/user/toggle_zombie_access/<username>', methods=['POST'])
@login_required
def api_admin_toggle_zombie_access(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    if username in users:
        # Admins können sich nicht selbst die Rechte entziehen
        if users[username].get('role') == 'admin':
             return jsonify({'error': 'Admin hat immer Zugriff'}), 400
             
        users[username]['can_use_zombie_bot'] = not users[username].get('can_use_zombie_bot', False)
        save_users(users)
        log_audit(current_user.username, 'Toggle Zombie-Bot Access', f"{username}: {users[username]['can_use_zombie_bot']}")
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/mode_requests')
@login_required
def api_admin_mode_requests():
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    return jsonify({'requests': bot.mode_change_requests})

@app.route('/api/admin/approve_mode_change/<username>', methods=['POST'])
@login_required
def api_admin_approve_mode_change(username):
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    if bot.approve_mode_change(username):
        log_audit(current_user.username, 'Approve Mode Change', username)
        return jsonify({'success': True})
    return jsonify({'error': 'Request not found'}), 404

@app.route('/api/admin/reject_mode_change/<username>', methods=['POST'])
@login_required
def api_admin_reject_mode_change(username):
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    if bot.reject_mode_change(username):
        log_audit(current_user.username, 'Reject Mode Change', username)
        return jsonify({'success': True})
    return jsonify({'error': 'Request not found'}), 404

@app.route('/api/admin/stats')
@login_required
def api_admin_stats():
    """ API für LKW-Statistiken """
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    start_str = request.args.get('start', '')
    end_str = request.args.get('end', '')
    
    if os.path.exists(LKW_STATS_FILE):
        try:
            with open(LKW_STATS_FILE, 'r') as f:
                content = f.read().strip()
                all_stats = json.loads(content) if content else []
        except (json.JSONDecodeError, ValueError):
            all_stats = []
    else:
        all_stats = []
    
    filtered_stats = []
    if not start_str and not end_str:
        filtered_stats = all_stats
    else:
        for stat in all_stats:
            try:
                stat_time = datetime.fromisoformat(stat['timestamp']).replace(tzinfo=None)
                include = True
                if start_str:
                    start_time = datetime.fromisoformat(start_str).replace(tzinfo=None)
                    if stat_time < start_time: include = False
                if end_str:
                    end_time = datetime.fromisoformat(end_str).replace(tzinfo=None)
                    if stat_time > end_time: include = False
                if include:
                    filtered_stats.append(stat)
            except Exception as e:
                logger.warning(f"LKW-Bot: Fehler beim Filtern der Statistik-Zeit: {e}")
                continue
    return jsonify({'trucks': filtered_stats})

@app.route('/api/admin/audit_log')
@login_required
def api_admin_audit_log():
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    if os.path.exists(AUDIT_LOG_FILE):
        with open(AUDIT_LOG_FILE, 'r') as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []
    return jsonify({'logs': logs[-100:]})

@app.route('/api/admin/maintenance', methods=['POST'])
@login_required
def api_admin_maintenance():
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    data = request.json
    enabled = data.get('enabled', False)
    bot.set_maintenance_mode(enabled)
    log_audit(current_user.username, 'Set Maintenance Mode', str(enabled))
    return jsonify({'success': True})

@app.route('/stats')
@login_required
def stats_page():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('stats.html', user=current_user)


# ================== NEUE GOLD-ZOMBIE-BOT ROUTES ==================

@app.route('/gold_zombies')
@login_required
def gold_zombies_page():
    """Zeigt das Gold-Zombie-Dashboard an"""
    if not current_user.can_use_zombie_bot:
        return redirect(url_for('index'))
    return render_template('gold_zombie.html', user=current_user)

@app.route('/api/gold_zombies/status')
@login_required
def api_gold_zombies_status():
    """Gibt den Status des Zombie-Bots zurück"""
    if not current_user.can_use_zombie_bot:
        return jsonify({'error': 'Unauthorized'}), 403
    
    runtime = "00:00:00"
    if zombie_bot.running and zombie_bot.start_time:
        elapsed = datetime.now() - zombie_bot.start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        runtime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return jsonify({
        'running': zombie_bot.running,
        'paused': zombie_bot.paused,
        'status': zombie_bot.status,
        'adb_connected': zombie_bot.adb_connected,
        'runtime': runtime,
        'used_50': zombie_bot.ausdauer_50_verwendet,
        'used_10': zombie_bot.ausdauer_10_verwendet,
        'deployed': zombie_bot.truppen_deployed
    })

@app.route('/api/gold_zombies/settings', methods=['GET', 'POST'])
@login_required
def api_gold_zombies_settings():
    """Holt oder setzt die Einstellungen UND die SSH-Config für den Zombie-Bot"""
    if not current_user.can_use_zombie_bot:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'POST':
        data = request.json
        
        zombie_bot.use_trupp_1 = data.get('use_trupp_1', False)
        zombie_bot.use_trupp_2 = data.get('use_trupp_2', True)
        zombie_bot.use_trupp_3 = data.get('use_trupp_3', True)
        zombie_bot.ausdauer_50_limit = int(data.get('stamina_50', 0))
        zombie_bot.ausdauer_10_limit = int(data.get('stamina_10', 0))
        zombie_bot.unbegrenzt_mode = data.get('unlimited', False)
        
        ssh_command = data.get('ssh_command', '').strip()
        ssh_password = data.get('ssh_password', '').strip()

        if not ssh_command:
            return jsonify({'error': 'SSH-Command ist erforderlich'}), 400
        
        parsed = parse_ssh_command(ssh_command)
        if not parsed:
            return jsonify({'error': 'Ungültiger SSH-Command'}), 400
        
        config = {
            'ssh_command': ssh_command,
            'ssh_password': ssh_password,
            'local_adb_port': parsed.get('local_port')
        }
        
        if save_ssh_config(config, GOLD_ZOMBIE_SSH_CONFIG_FILE):
            zombie_bot.ssh_config = config
            if zombie_bot.running:
                logger.info("Zombie-Bot läuft, starte SSH-Tunnel neu...")
                zombie_bot.close_ssh_tunnel()
                time.sleep(1)
                zombie_bot.setup_ssh_tunnel()
            log_audit(current_user.username, 'Update Zombie-Bot Config')
            return jsonify({'success': True, 'message': 'Einstellungen & SSH-Konfiguration gespeichert'})
        else:
            return jsonify({'error': 'Fehler beim Speichern der SSH-Config'}), 500

    else:
        # GET
        ssh_config = load_ssh_config(GOLD_ZOMBIE_SSH_CONFIG_FILE)
        return jsonify({
            'use_trupp_1': zombie_bot.use_trupp_1,
            'use_trupp_2': zombie_bot.use_trupp_2,
            'use_trupp_3': zombie_bot.use_trupp_3,
            'stamina_50': zombie_bot.ausdauer_50_limit,
            'stamina_10': zombie_bot.ausdauer_10_limit,
            'unlimited': zombie_bot.unbegrenzt_mode,
            'ssh_command': ssh_config.get('ssh_command', ''),
            'ssh_password': ssh_config.get('ssh_password', ''),
            'local_adb_port': ssh_config.get('local_adb_port'),
            'last_updated': ssh_config.get('last_updated', None)
        })

@app.route('/api/gold_zombies/start', methods=['POST'])
@login_required
def api_gold_zombies_start():
    if not current_user.can_use_zombie_bot:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if not (zombie_bot.use_trupp_1 or zombie_bot.use_trupp_2 or zombie_bot.use_trupp_3):
        return jsonify({'error': 'Mindestens eine Truppe muss ausgewählt sein!'}), 400
    
    if not zombie_bot.unbegrenzt_mode:
        if zombie_bot.ausdauer_50_limit <= 0 and zombie_bot.ausdauer_10_limit <= 0:
            return jsonify({'error': 'Mindestens ein Ausdauer-Limit muss > 0 sein!'}), 400

    zombie_bot.start()
    log_audit(current_user.username, 'Start Zombie-Bot')
    return jsonify({'success': True})

@app.route('/api/gold_zombies/pause', methods=['POST'])
@login_required
def api_gold_zombies_pause():
    if not current_user.can_use_zombie_bot:
        return jsonify({'error': 'Unauthorized'}), 403
    zombie_bot.pause()
    log_audit(current_user.username, 'Pause Zombie-Bot')
    return jsonify({'success': True})

@app.route('/api/gold_zombies/stop', methods=['POST'])
@login_required
def api_gold_zombies_stop():
    if not current_user.can_use_zombie_bot:
        return jsonify({'error': 'Unauthorized'}), 403
    zombie_bot.stop()
    log_audit(current_user.username, 'Stop Zombie-Bot')
    return jsonify({'success': True})

@app.route('/api/gold_zombies/test_ssh', methods=['POST'])
@login_required
def api_gold_zombies_test_ssh():
    """ Testet die Zombie-Bot SSH-Config """
    if not current_user.can_use_zombie_bot:
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        zombie_bot.close_ssh_tunnel()
        time.sleep(1)
        if zombie_bot.setup_ssh_tunnel():
            return jsonify({'success': True, 'message': 'Zombie-Bot SSH-Tunnel und ADB erfolgreich verbunden'})
        else:
            return jsonify({'success': False, 'message': 'Zombie-Bot Verbindung fehlgeschlagen - Bitte Logs prüfen'}), 400
    except Exception as e:
        logger.error(f"Zombie-Bot Fehler beim Testen der SSH-Verbindung: {e}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

# ================== Main ==================

if __name__ == '__main__':
    init_users()
    
    lkw_ssh_config = load_ssh_config(LKW_SSH_CONFIG_FILE)
    if lkw_ssh_config.get('ssh_command'):
        logger.info("LKW-Bot SSH-Konfiguration geladen")
    else:
        logger.warning("⚠️  KEINE LKW-BOT SSH-KONFIGURATION VORHANDEN!")

    zombie_ssh_config = load_ssh_config(GOLD_ZOMBIE_SSH_CONFIG_FILE)
    if zombie_ssh_config.get('ssh_command'):
        logger.info("Gold-Zombie-Bot SSH-Konfiguration geladen")
    else:
        logger.warning("⚠️  KEINE GOLD-ZOMBIE-BOT SSH-KONFIGURATION VORHANDEN!")
    
    logger.info("Starte Dual-Bot Web-Interface v3.1 (Hotfix)...")
    app.run(host='0.0.0.0', port=5000, debug=False)