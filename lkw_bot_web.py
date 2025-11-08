#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LKW-Bot für Last War mit Web-Interface
Optimiert für Raspberry Pi und VMOSCloud über SSH-Tunnel
Version 2.2 - V2-SSH-Logik mit V1-Spiellogik/Koordinaten fusioniert
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
        'admin_dashboard': 'Admin',
        'use_timer': 'Timer verwenden',
        'timer_minutes': 'Laufzeit (Minuten)',
        'timer_remaining': 'Verbleibende Zeit',
        'request_mode_change': 'Modus-Wechsel anfordern',
        'mode_change_requested': 'Modus-Wechsel angefordert',
        'maintenance_active': 'Wartungsarbeiten aktiv',
        'maintenance_message': 'Bot ist im Wartungsmodus - Bitte warten Sie',
        'maintenance_admin_info': 'Admin-Modus: Sie können weiterhin alle Funktionen nutzen'
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
        'use_timer': 'Use timer',
        'timer_minutes': 'Runtime (minutes)',
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
        'admin_dashboard': 'Admin',
        'timer_remaining': 'Time remaining',
        'request_mode_change': 'Request mode change',
        'mode_change_requested': 'Mode change requested',
        'maintenance_active': 'Maintenance active',
        'maintenance_message': 'Bot is in maintenance mode - Please wait',
        'maintenance_admin_info': 'Admin mode: You can still use all functions'
    }
}


# ================== SSH Konfiguration (V2) ==================

def load_ssh_config():
    """Lade SSH-Konfiguration aus Datei"""
    if os.path.exists(SSH_CONFIG_FILE):
        try:
            with open(SSH_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Fehler beim Laden der SSH-Konfiguration: {e}")
    
    # Standard-Konfiguration
    return {
        'ssh_command': '',
        'ssh_password': '',
        'local_adb_port': 5839, # Standard-Fallback
        'last_updated': None
    }

def save_ssh_config(config):
    """Speichere SSH-Konfiguration"""
    config['last_updated'] = datetime.now().isoformat()
    try:
        with open(SSH_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info("SSH-Konfiguration gespeichert")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Speichern der SSH-Konfiguration: {e}")
        return False

def parse_ssh_command(ssh_command):
    """Extrahiere Informationen aus dem SSH-Command"""
    try:
        # Beispiel: ssh -oHostKeyAlgorithms=+ssh-rsa 10.0.4.206_1762615280757@103.237.100.130 -p 1824 -L 8583:adb-proxy:50438 -Nf
        parts = ssh_command.split()
        
        user_host = None
        port = None
        local_port = None
        remote_info = None
        
        for i, part in enumerate(parts):
            if '@' in part and not part.startswith('-'):
                user_host = part
            elif part == '-p' and i + 1 < len(parts):
                port = parts[i + 1]
            elif part == '-L' and i + 1 < len(parts):
                tunnel_info = parts[i + 1]
                local_port = tunnel_info.split(':')[0]
                remote_info = tunnel_info
        
        if not local_port:
             logger.warning("Konnte Local Port nicht aus SSH-Command extrahieren")
             return None

        return {
            'user_host': user_host,
            'port': port,
            'local_port': int(local_port),
            'remote_info': remote_info,
            'full_command': ssh_command
        }
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

TEMPLATE_FILE = 'rentier_template.png' # Name der Template-Datei
STAERKEN_FILE = 'lkw_staerken.txt'     # Datei für bereits geteilte Stärken
USERS_FILE = 'users.json'
AUDIT_LOG_FILE = 'audit_log.json'
MAINTENANCE_FILE = 'maintenance.json'
STATS_FILE = 'truck_stats.json'        # Datei für Statistiken (ersetzt truck_data.json)
MODE_REQUESTS_FILE = 'mode_requests.json'
SSH_CONFIG_FILE = 'ssh_config.json'

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


# ================== User System (V2-Logik) ==================

class User(UserMixin):
    def __init__(self, username, password, role='user', blocked=False, can_choose_share_mode=True, forced_share_mode=None):
        self.id = username
        self.username = username
        self.password = password
        self.role = role
        self.blocked = blocked
        self.can_choose_share_mode = can_choose_share_mode
        self.forced_share_mode = forced_share_mode

def init_users():
    """Initialisiere Benutzer-Datenbank"""
    if not os.path.exists(USERS_FILE):
        users = {
            'admin': {
                'password': generate_password_hash('rREq8/1F4m#'),
                'role': 'admin',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None
            },
            'All4One': {
                'password': generate_password_hash('52B1z_'),
                'role': 'user',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None
            },
            'Server39': {
                'password': generate_password_hash('!3Z4d5'),
                'role': 'user',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None
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
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    
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
        return User(
            username, 
            user_data['password'], 
            user_data['role'], 
            user_data.get('blocked', False),
            user_data.get('can_choose_share_mode', True),
            user_data.get('forced_share_mode', None)
        )
    return None

# Initialisiere Users beim Start
init_users()

# ================== Bot-Steuerung (V2-Basis) ==================

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
        
        # Timer-Funktionen
        self.use_timer = False
        self.timer_duration_minutes = 60
        self.timer_start_time = None
        self.timer_thread = None
        
        # Einstellungen
        self.use_limit = False
        self.strength_limit = 60.0
        self.use_server_filter = False
        self.server_number = "49"
        self.reset_interval = 15
        self.share_mode = "world"
        self.adb_connected = False
        
        # Mode-Change-Requests
        self.mode_change_requests = self.load_mode_change_requests()
        
        # Fehlerüberwachung
        self.last_success_time = time.time()
        self.error_count = 0
        self.maintenance_mode = self.load_maintenance_mode()
        
        # SSH-Konfiguration laden
        self.ssh_config = load_ssh_config()
        
        # Statistiken
        self.trucks_processed = 0
        self.trucks_shared = 0
        self.trucks_skipped = 0
        
        # Maintenance Mode
        self.maintenance_mode = self.load_maintenance_mode()
        self.last_success_time = time.time()  # Letzte erfolgreiche Aktion
        self.no_truck_threshold = 300  # 5 Minuten ohne Fund = Problem
        
    def load_mode_change_requests(self):
        """Lade Mode-Change-Requests"""
        if os.path.exists(MODE_REQUESTS_FILE):
            try:
                with open(MODE_REQUESTS_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def save_mode_change_requests(self):
        """Speichere Mode-Change-Requests"""
        with open(MODE_REQUESTS_FILE, 'w') as f:
            json.dump(self.mode_change_requests, f, indent=2)
    
    def request_mode_change(self, username, requested_mode):
        """Fordere Modus-Wechsel an"""
        self.mode_change_requests[username] = {
            'requested_mode': requested_mode,
            'timestamp': datetime.now().isoformat(),
            'status': 'pending'
        }
        self.save_mode_change_requests()
        logger.info(f"Mode change requested by {username}: {requested_mode}")
        
    def approve_mode_change(self, username):
        """Genehmige Modus-Wechsel"""
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
        """Lehne Modus-Wechsel ab"""
        if username in self.mode_change_requests:
            self.mode_change_requests[username]['status'] = 'rejected'
            self.save_mode_change_requests()
            return True
        return False
    
    def get_remaining_time_seconds(self):
        """Gibt die verbleibende Zeit in Sekunden zurück"""
        if not self.use_timer or not self.timer_start_time:
            return None
        
        elapsed = time.time() - self.timer_start_time
        remaining = (self.timer_duration_minutes * 60) - elapsed
        return max(0, remaining)
    
    def check_timer(self):
        """Überprüft den Timer und stoppt den Bot wenn Zeit abgelaufen"""
        while self.running and self.use_timer:
            remaining = self.get_remaining_time_seconds()
            if remaining is not None and remaining <= 0:
                logger.info(f"Timer abgelaufen - Bot wird gestoppt")
                self.stop()
                break
            time.sleep(1)
        
    def load_maintenance_mode(self):
        """Lade Maintenance-Status"""
        if os.path.exists(MAINTENANCE_FILE):
            try:
                with open(MAINTENANCE_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('enabled', False)
            except json.JSONDecodeError:
                return False
        return False
    
    def set_maintenance_mode(self, enabled):
        """Setze Maintenance-Mode"""
        self.maintenance_mode = enabled
        with open(MAINTENANCE_FILE, 'w') as f:
            json.dump({'enabled': enabled}, f)
        logger.info(f"Maintenance Mode: {'Aktiviert' if enabled else 'Deaktiviert'}")
    
    def check_auto_maintenance(self):
        """Prüfe ob automatischer Maintenance-Mode aktiviert werden soll"""
        if self.maintenance_mode:
            return  # Bereits im Maintenance-Mode
        
        time_since_success = time.time() - self.last_success_time
        if time_since_success > self.no_truck_threshold:
            logger.warning(f"Keine LKWs seit {int(time_since_success)}s - aktiviere Maintenance-Mode")
            self.set_maintenance_mode(True)
    
    def log_truck_stat(self, strength, server):
        """Speichere Truck-Statistik"""
        if not os.path.exists(STATS_FILE):
            stats = []
        else:
            try:
                with open(STATS_FILE, 'r') as f:
                    content = f.read().strip()
                    if content:
                        stats = json.loads(content)
                    else:
                        stats = []
            except (json.JSONDecodeError, ValueError):
                logger.error(f"Korrupte Stats-Datei, erstelle neue")
                stats = []
        
        tz = pytz.timezone('Europe/Berlin')
        timestamp = datetime.now(tz).isoformat()
        
        stats.append({
            'strength': strength,
            'server': server,
            'timestamp': timestamp,
            'user': self.current_user
        })
        
        # Nur letzte 30 Tage behalten (Logik aus altem Skript übernommen)
        cutoff = datetime.now(tz) - timedelta(days=30)
        stats = [s for s in stats if datetime.fromisoformat(s['timestamp']) > cutoff]
        
        try:
            with open(STATS_FILE, 'w') as f:
                json.dump(stats, f, indent=2)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Stats: {e}")

        # Erfolgreich -> Reset Timer (Logik aus altem Skript)
        self.last_success_time = time.time()
        if self.maintenance_mode:
            logger.info("LKW gefunden - deaktiviere Maintenance-Mode")
            self.set_maintenance_mode(False)
    
    # =========================================================================
    # NEUE SSH/ADB FUNKTIONEN (V2 LOGIK)
    # =========================================================================

    def setup_ssh_tunnel(self):
        """Erstellt SSH-Tunnel basierend auf der ssh_config.json (V2 LOGIK)"""
        self.ssh_config = load_ssh_config() # Lade die neuesten Daten
        
        ssh_command_str = self.ssh_config.get('ssh_command')
        ssh_password = self.ssh_config.get('ssh_password') # Das ist dein "Connection Key"
        local_port = self.ssh_config.get('local_adb_port')

        if not ssh_command_str or not local_port:
            logger.error("SSH-Command oder Local Port fehlt in ssh_config.json")
            self.status = "SSH-Konfig fehlt"
            self.adb_connected = False
            return False
        
        self.close_ssh_tunnel()
        
        cmd_parts = ssh_command_str.split()
        
        if ssh_password:
            if subprocess.run(['which', 'sshpass'], capture_output=True).returncode != 0:
                logger.error("="*50)
                logger.error("FEHLER: 'sshpass' ist nicht installiert!")
                logger.error("Bitte installieren: sudo apt-get update && sudo apt-get install -y sshpass")
                logger.error("="*50)
                self.status = "sshpass fehlt"
                self.adb_connected = False
                return False
            
            cmd = ['sshpass', '-p', ssh_password] + cmd_parts
        else:
            cmd = cmd_parts
        
        logger.info(f"Starte SSH-Tunnel auf Port {local_port}...")
        
        try:
            cmd = [part for part in cmd if part not in ['-Nf', '-N', '-f']]
            cmd.extend(['-N']) 
            
            self.ssh_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            logger.info("Warte 7 Sekunden auf SSH-Verbindungsaufbau...")
            time.sleep(7) 
            
            poll = self.ssh_process.poll()
            if poll is not None:
                stderr_output = self.ssh_process.stderr.read()
                logger.error(f"SSH-Tunnel konnte nicht gestartet werden. Fehler: {stderr_output}")
                self.status = "SSH-Fehler"
                self.adb_connected = False
                return False
            
            logger.info(f"SSH-Tunnel aktiv. Verbinde ADB mit localhost:{local_port}...")
            adb_cmd = ['adb', 'connect', f'localhost:{local_port}']
            adb_result = subprocess.run(adb_cmd, capture_output=True, text=True, timeout=10)
            
            if 'connected' in adb_result.stdout.lower() or 'already' in adb_result.stdout.lower():
                logger.info("ADB erfolgreich verbunden")
                self.adb_connected = True
                return True
            else:
                logger.warning(f"ADB-Verbindung fehlgeschlagen: {adb_result.stdout}")
                self.close_ssh_tunnel() 
                self.adb_connected = False
                return False

        except Exception as e:
            logger.error(f"Fehler beim Starten des SSH-Tunnels: {e}")
            self.close_ssh_tunnel()
            self.adb_connected = False
            return False
    
    def close_ssh_tunnel(self):
        """Schließt SSH-Tunnel und ADB-Verbindung (V2 LOGIK)"""
        try:
            local_port = self.ssh_config.get('local_adb_port', 8583) 
            
            logger.info(f"Trenne ADB von localhost:{local_port}")
            subprocess.run(['adb', 'disconnect', f'localhost:{local_port}'], timeout=5, capture_output=True)
            
            if self.ssh_process:
                logger.info("Beende SSH-Tunnel-Prozess...")
                self.ssh_process.terminate()
                self.ssh_process.wait(timeout=5)
                self.ssh_process = None
            
            logger.info(f"Kille alle verbleibenden SSH-Prozesse auf Port {local_port}")
            pkill_cmd = f"pkill -f 'ssh.*{local_port}:adb-proxy'"
            subprocess.run(pkill_cmd, shell=True, capture_output=True)

            self.adb_connected = False
            logger.info("SSH-Tunnel und ADB sauber getrennt")
        except Exception as e:
            logger.error(f"Fehler beim Schließen des Tunnels: {e}")
    
    def make_screenshot(self, filename='screen.png'):
        """Erstellt Screenshot über ADB (V2-Logik)"""
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port:
                logger.error("ADB-Port nicht konfiguriert")
                return False
                
            adb_device = f'localhost:{local_port}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'screencap', '-p', f'/sdcard/{filename}'], 
                         timeout=10, capture_output=True)
            subprocess.run(['adb', '-s', adb_device, 'pull', f'/sdcard/{filename}', filename], 
                         timeout=10, capture_output=True)
            return os.path.exists(filename)
        except Exception as e:
            logger.error(f"Screenshot-Fehler: {e}")
            return False
    
    def click(self, x, y):
        """Klickt auf Koordinaten (V2-Logik)"""
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port: return False
            
            adb_device = f'localhost:{local_port}'
            # Klick-Logging aus alter Logik übernommen
            logger.info(f"Klicke auf ({x}, {y})")
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'tap', str(x), str(y)], capture_output=True, timeout=5)
            # Sleep aus alter Logik übernommen
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"Klick-Fehler: {e}")
            return False
    
    def swipe(self, x1, y1, x2, y2, duration=500):
        """Swipe-Geste (V2-Logik)"""
        try:
            local_port = self.ssh_config.get('local_adb_port')
            if not local_port: return False
                
            adb_device = f'localhost:{local_port}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'swipe', 
                          str(x1), str(y1), str(x2), str(y2), str(duration)], capture_output=True)
            return True
        except Exception as e:
            logger.error(f"Swipe-Fehler: {e}")
            return False
    
    # =========================================================================
    # SPIEL-FUNKTIONEN (Logik aus V1-Skript)
    # =========================================================================
    
    def ocr_staerke(self):
        """Liest Stärke per OCR"""
        try:
            img = Image.open('info.png')
            staerke_img = img.crop(STAERKE_BOX)
            staerke_img.save('staerke_ocr.png')
            
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

    def ocr_server(self):
        """Liest Server-Text per OCR (Hilfsfunktion für Stats)"""
        try:
            img = Image.open('info.png')
            server_img = img.crop(SERVER_BOX)
            server_text = pytesseract.image_to_string(server_img, lang='eng').strip()
            logger.info(f"OCR Server: '{server_text}'")
            
            s_txt = re.sub(r'[^0-9]', '', server_text) # Nur Ziffern behalten
            return s_txt if s_txt else "Unknown"
        except Exception as e:
            logger.error(f"Server-OCR-Fehler: {e}")
            return "Unknown"

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
            template = cv2.imread(TEMPLATE_FILE) # TEMPLATE_FILE ist 'rentier_template.png'
            
            if screenshot is None:
                logger.error("Screenshot-Datei 'screen.png' konnte nicht gelesen werden")
                return None
            if template is None:
                logger.error(f"Template-Datei '{TEMPLATE_FILE}' konnte nicht gelesen werden")
                return None
                
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= 0.40) # Threshold aus V1-Skript
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
                
                # Automatische Komma-Korrektur (Logik aus V1-Skript)
                if zahl >= 100 and '.' not in match.group(1) and ',' not in match.group(1):
                    zahl = zahl / 10
                    logger.info(f"Komma-Korrektur: {match.group(1)}M → {zahl}M")
                
                return zahl
            except ValueError:
                return None
        return None

    def load_staerken(self):
        """Lädt bereits geteilte Stärken (V2-Funktion, V1-Logik)"""
        if os.path.exists(STAERKEN_FILE):
            try:
                with open(STAERKEN_FILE, 'r', encoding="utf-8") as f:
                    return f.read().splitlines()
            except Exception as e:
                logger.error(f"Fehler beim Laden der Stärken: {e}")
                return []
        return []
    
    def save_staerke(self, staerke):
        """Speichert geteilte Stärke (V2-Funktion, V1-Logik)"""
        try:
            with open(STAERKEN_FILE, "a", encoding="utf-8") as f:
                f.write(staerke + "\n")
            logger.info(f"Stärke {staerke} notiert")
        except Exception as e:
            logger.error(f"Fehler beim Notieren der Stärke: {e}")
    
    def reset_staerken(self):
        """Setzt die Stärken-Liste zurück (V2-Funktion, V1-Logik)"""
        try:
            with open(STAERKEN_FILE, "w", encoding="utf-8") as f:
                f.write("")
            logger.info("Stärken-Liste zurückgesetzt")
        except Exception as e:
            logger.error(f"Reset-Fehler: {e}")

    # =========================================================================
    # BOT-HAUPTSCHLEIFE (V1-Spiellogik fusioniert mit V2-Funktionen)
    # =========================================================================
    
    def bot_loop(self):
        """Hauptschleife des Bots (LOGIK AUS ALTEM SKRIPT)"""
        logger.info("Bot-Schleife gestartet")
        
        # Setup SSH-Tunnel (V2-Funktion)
        if not self.setup_ssh_tunnel():
            self.status = "Fehler: SSH-Tunnel konnte nicht aufgebaut werden"
            self.running = False
            return
        
        # Reset-Timer starten (V2-Funktion)
        reset_thread = threading.Thread(target=self.reset_timer, daemon=True)
        reset_thread.start()
        
        # Auto-Stop Timer starten (V2-Logik)
        if self.use_timer:
            self.timer_start_time = time.time()
            self.timer_thread = threading.Thread(target=self.check_timer, daemon=True)
            self.timer_thread.start()
            logger.info(f"Auto-Stop Timer gestartet für {self.timer_duration_minutes} Minuten")
        
        while self.running:
            if self.paused:
                self.status = "Pausiert"
                time.sleep(1)
                continue
            
            # Maintenance-Mode Check (V2-Logik)
            if self.maintenance_mode:
                self.status = "Maintenance-Mode"
                self.last_action = "Wartungsarbeiten - Bot pausiert"
                time.sleep(10)
                continue

            try:
                self.status = "Läuft - Suche LKWs..."
                self.last_action = "Screenshot erstellen"
                
                if not self.make_screenshot('screen.png'): # V2-Funktion
                    self.last_action = "Fehler: Screenshot fehlgeschlagen"
                    time.sleep(5)
                    continue
                
                time.sleep(0.5)
                treffer = self.rentier_lkw_finden() # Alte Logik-Funktion
                
                if not treffer:
                    self.last_action = "Kein LKW gefunden - ESC"
                    self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1]) # V2-Funktion, Alte Coords
                    self.trucks_processed += 1
                    continue
                
                self.last_action = f"LKW gefunden bei {treffer[0]}"
                logger.info(f"Treffer bei: {treffer[0]}")
                
                # Klicke auf LKW (mit Offset)
                lx = treffer[0][0] + 5  # Angepasster Offset für kleineren Screen
                ly = treffer[0][1] + 5
                self.click(lx, ly) # V2-Funktion
                
                if not self.make_screenshot('info.png'): # V2-Funktion
                    self.last_action = "Fehler: Info-Screenshot fehlgeschlagen"
                    continue
                
                # Server-Check
                if self.use_server_filter:
                    self.last_action = "Prüfe Server..."
                    if not self.ist_server_passend(): # Alte Logik-Funktion
                        self.last_action = f"Falscher Server - ESC"
                        self.click(COORDS_NEW['esc'][0], COORDS_NEW['esc'][1]) # V2-Funktion
                        self.trucks_skipped += 1
                        self.trucks_processed += 1
                        continue
                
                # Stärke auslesen
                self.last_action = "Lese Stärke..."
                staerke = self.ocr_staerke() # Alte Logik-Funktion
                wert = self.staerke_float_wert(staerke) # Alte Logik-Funktion
                logger.info(f"Stärke gelesen: '{staerke}' Wert: {wert}")
                
                # Stärke-Check
                limit_passed = True
                if self.use_limit and wert is not None:
                    if wert > self.strength_limit:
                        limit_passed = False
                        self.last_action = f"Stärke {wert} > {self.strength_limit} - übersprungen"
                
                # Prüfe auf None, Limit ODER ob Stärke bekannt ist
                if wert is None or not limit_passed or (staerke in self.load_staerken()):
                    if wert is None:
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
                self.save_staerke(staerke) # V2-Funktion
                
                # Server auslesen für Statistik
                server = self.ocr_server() # Eigene Hilfsfunktion
                
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
                
                # Statistik speichern
                self.log_truck_stat(staerke, server) # V2-Funktion
                
            except Exception as e:
                logger.error(f"Fehler in Bot-Schleife: {e}")
                import traceback
                logger.error(traceback.format_exc()) # Besser für Debugging
                self.last_action = f"Fehler: {str(e)}"
                time.sleep(5)
            
            # Prüfe Maintenance-Mode (V2-Funktion)
            self.check_auto_maintenance()
        
        # Cleanup
        self.close_ssh_tunnel() # V2-Funktion
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
        """Startet den Bot (V2-Logik)"""
        if not self.running:
            self.running = True
            self.paused = False
            self.thread = threading.Thread(target=self.bot_loop, daemon=True)
            self.thread.start()
            logger.info(f"Bot gestartet von {self.current_user}")
    
    def pause(self):
        """Pausiert/Fortsetzt den Bot (V2-Logik)"""
        if self.running:
            self.paused = not self.paused
            logger.info(f"Bot {'pausiert' if self.paused else 'fortgesetzt'}")
    
    def stop(self):
        """Stoppt den Bot (V2-Logik)"""
        self.running = False
        self.use_timer = False  # Timer deaktivieren
        self.timer_start_time = None
        if self.thread:
            self.thread.join(timeout=10)
        if self.timer_thread:
            self.timer_thread.join(timeout=5)
        logger.info("Bot gestoppt")

# Globale Bot-Instanz
bot = BotController()

# ================== Flask Routes (V2-Logik) ==================

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
    remaining_time = None
    if bot.use_timer:
        remaining_seconds = bot.get_remaining_time_seconds()
        if remaining_seconds:
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
        log_audit(current_user.username, 'Start Bot', f'Timer: {bot.use_timer}, Duration: {bot.timer_duration_minutes}min')
    
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
        
        log_audit(current_user.username, 'Change Settings', 
                 f"limit={data.get('use_limit')}, strength={data.get('strength_limit')}, "
                 f"server={data.get('server_number')}, mode={bot.share_mode}, "
                 f"timer={bot.use_timer}, duration={bot.timer_duration_minutes}")
        
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
    log_audit(current_user.username, 'Reset Statistics', '')
    return jsonify({'success': True})


# ================== SSH Configuration Routes (V2-Logik) ==================

@app.route('/api/admin/ssh_config', methods=['GET', 'POST'])
@login_required
def api_admin_ssh_config():
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
        
        local_port = parsed.get('local_port')
        
        config = {
            'ssh_command': ssh_command,
            'ssh_password': ssh_password,
            'local_adb_port': local_port
        }
        
        if save_ssh_config(config):
            bot.ssh_config = config
            
            if bot.running:
                logger.info("Bot läuft, starte SSH-Tunnel neu...")
                bot.close_ssh_tunnel()
                time.sleep(1)
                bot.setup_ssh_tunnel()
            
            log_audit(current_user.username, 'Update SSH Config', 'SSH-Konfiguration aktualisiert')
            return jsonify({'success': True, 'message': 'SSH-Konfiguration gespeichert'})
        else:
            return jsonify({'error': 'Fehler beim Speichern'}), 500
    
    else:
        config = load_ssh_config()
        return jsonify({
            'ssh_command': config.get('ssh_command', ''),
            'ssh_password': config.get('ssh_password', ''),
            'local_adb_port': config.get('local_adb_port', 5839),
            'last_updated': config.get('last_updated', None)
        })

@app.route('/api/admin/test_ssh', methods=['POST'])
@login_required
def api_admin_test_ssh():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        bot.close_ssh_tunnel()
        time.sleep(1)
        
        if bot.setup_ssh_tunnel():
            return jsonify({
                'success': True,
                'message': 'SSH-Tunnel und ADB erfolgreich verbunden'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Verbindung fehlgeschlagen - Bitte Logs prüfen'
            }), 400
            
    except Exception as e:
        logger.error(f"Fehler beim Testen der SSH-Verbindung: {e}")
        return jsonify({
            'success': False,
            'message': f'Fehler: {str(e)}'
        }), 500

# ================== Admin Routes (V2-Logik) ==================

@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html', user=current_user)

@app.route('/api/admin/users')
@login_required
def api_admin_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    user_list = []
    for username, data in users.items():
        user_list.append({
            'username': username,
            'role': data['role'],
            'blocked': data.get('blocked', False),
            'can_choose_share_mode': data.get('can_choose_share_mode', True),
            'forced_share_mode': data.get('forced_share_mode', None)
        })
    return jsonify({'users': user_list})

@app.route('/api/admin/user/toggle_block/<username>', methods=['POST'])
@login_required
def api_admin_toggle_block(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
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
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    users = load_users()
    if username in users:
        users[username]['can_choose_share_mode'] = data.get('can_choose', True)
        users[username]['forced_share_mode'] = data.get('forced_mode', None)
        save_users(users)
        log_audit(current_user.username, 'Set User Share Mode', f"{username}: {data}")
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/mode_requests')
@login_required
def api_admin_mode_requests():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({'requests': bot.mode_change_requests})

@app.route('/api/admin/approve_mode_change/<username>', methods=['POST'])
@login_required
def api_admin_approve_mode_change(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if bot.approve_mode_change(username):
        log_audit(current_user.username, 'Approve Mode Change', username)
        return jsonify({'success': True})
    return jsonify({'error': 'Request not found'}), 404

@app.route('/api/admin/reject_mode_change/<username>', methods=['POST'])
@login_required
def api_admin_reject_mode_change(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if bot.reject_mode_change(username):
        log_audit(current_user.username, 'Reject Mode Change', username)
        return jsonify({'success': True})
    return jsonify({'error': 'Request not found'}), 404

@app.route('/api/admin/stats')
@login_required
def api_admin_stats():
    """API für Truck-Statistiken"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    start_str = request.args.get('start', '')
    end_str = request.args.get('end', '')
    
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    all_stats = json.loads(content)
                else:
                    all_stats = []
        except (json.JSONDecodeError, ValueError):
            logger.error("Fehler beim Laden der Statistiken")
            all_stats = []
    else:
        all_stats = []
    
    # Filtern nach Zeitbereich
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
                    if stat_time < start_time:
                        include = False
                
                if end_str:
                    end_time = datetime.fromisoformat(end_str).replace(tzinfo=None)
                    if stat_time > end_time:
                        include = False
                
                if include:
                    filtered_stats.append(stat)
            except Exception as e:
                logger.warning(f"Fehler beim Filtern der Statistik-Zeit: {e} (Wert: {stat.get('timestamp')})")
                continue
    
    return jsonify({'trucks': filtered_stats})

@app.route('/api/admin/audit_log')
@login_required
def api_admin_audit_log():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
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
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
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

if __name__ == '__main__':
    init_users()
    
    ssh_config = load_ssh_config()
    if ssh_config.get('ssh_command'):
        logger.info("SSH-Konfiguration geladen")
        logger.info(f"Letzte Aktualisierung: {ssh_config.get('last_updated', 'Unbekannt')}")
    else:
        logger.warning("⚠️  KEINE SSH-KONFIGURATION VORHANDEN!")
        logger.warning("Bitte im Admin-Panel konfigurieren: http://<deine-ip>:5000/admin")
    
    logger.info("Starte LKW-Bot Web-Interface v2.2 (Fusioniert)...")
    app.run(host='0.0.0.0', port=5000, debug=False)