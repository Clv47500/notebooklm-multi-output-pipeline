#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_chrome_cdp.py — Configuration automatique Chrome pour NLM Pipeline v2
Christian Levannier — 04 juin 2026

Objectif : ajouter --remote-debugging-port=9222 à tous les raccourcis Chrome
afin que le pipeline_runner_v2.py puisse s'authentifier AUTOMATIQUEMENT,
sans intervention manuelle, chaque fois que Chrome est ouvert.

À exécuter UNE SEULE FOIS. Après cela, le pipeline fonctionne en autonomie totale.

Usage :
    python setup_chrome_cdp.py           # Mode interactif (confirme avant modification)
    python setup_chrome_cdp.py --silent  # Mode silencieux (applique sans confirmation)
    python setup_chrome_cdp.py --check   # Vérifie l'état sans modifier
    python setup_chrome_cdp.py --undo    # Retire le flag CDP des raccourcis
"""

import argparse
import os
import sys
import io
import subprocess
from pathlib import Path
import winreg

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CDP_FLAG = "--remote-debugging-port=9222"
CDP_PORT  = 9222

# ─── Chemins à scanner ──────────────────────────────────────────────────────
SHORTCUT_LOCATIONS = [
    Path.home() / "Desktop",
    Path(os.environ.get("APPDATA",""))    / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA",""))    / "Microsoft/Internet Explorer/Quick Launch",
    Path(os.environ.get("APPDATA",""))    / "Microsoft/Windows/Start Menu",
    Path(os.environ.get("LOCALAPPDATA","")) / "Microsoft/Windows/WinX",
]
TASKBAR_PATH = (
    Path(os.environ.get("APPDATA","")) /
    "Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar"
)
SHORTCUT_LOCATIONS.append(TASKBAR_PATH)


def log(msg, level="INFO"):
    icons = {"INFO": "  ·", "OK": "  ✓", "WARN": "  !", "ERR": "  ✗", "STEP": "\n→"}
    print(f"{icons.get(level,'  ')} {msg}")


def get_chrome_exe():
    """Trouve l'exécutable Chrome."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path(os.environ.get("LOCALAPPDATA","")) /
            "Google/Chrome/Application/chrome.exe"),
    ]
    return next((p for p in candidates if Path(p).exists()), None)


def read_shortcut(lnk_path):
    """
    Lit la cible et les arguments d'un raccourci .lnk via PowerShell.
    Retourne (target, arguments) ou (None, None).
    """
    ps = (
        "$sh = New-Object -COM WScript.Shell;"
        f"$lnk = $sh.CreateShortcut('{str(lnk_path)}');"
        "Write-Output ($lnk.TargetPath + '|||' + $lnk.Arguments)"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10
        )
        parts = r.stdout.strip().split("|||", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    except Exception:
        pass
    return None, None


def write_shortcut(lnk_path, target, arguments):
    """Met à jour les arguments d'un raccourci .lnk via PowerShell."""
    escaped_args = arguments.replace("'", "''")
    escaped_lnk  = str(lnk_path).replace("'", "''")
    escaped_tgt  = target.replace("'", "''")
    ps = (
        "$sh = New-Object -COM WScript.Shell;"
        f"$lnk = $sh.CreateShortcut('{escaped_lnk}');"
        f"$lnk.TargetPath = '{escaped_tgt}';"
        f"$lnk.Arguments = '{escaped_args}';"
        "$lnk.Save()"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10
        )
        return r.returncode == 0
    except Exception:
        return False


def find_chrome_shortcuts():
    """Trouve tous les raccourcis Chrome dans les emplacements standard."""
    chrome_exe = get_chrome_exe()
    shortcuts  = []

    for folder in SHORTCUT_LOCATIONS:
        if not folder.exists():
            continue
        for lnk in folder.rglob("*.lnk"):
            target, args = read_shortcut(lnk)
            if not target:
                continue
            if "chrome" in target.lower() and target.endswith(".exe"):
                shortcuts.append({
                    "path":    lnk,
                    "target":  target,
                    "args":    args or "",
                    "has_cdp": CDP_FLAG in (args or ""),
                })

    return shortcuts


def check_cdp_status():
    """Vérifie l'état CDP de tous les raccourcis Chrome."""
    import socket
    log("Vérification état CDP", "STEP")

    # Chrome en cours ?
    active = False
    try:
        s = socket.create_connection(("127.0.0.1", CDP_PORT), timeout=2)
        s.close()
        active = True
        log(f"Chrome CDP actif sur port {CDP_PORT} ✅", "OK")
    except:
        log(f"Chrome CDP non actif (port {CDP_PORT})", "WARN")

    shortcuts = find_chrome_shortcuts()
    log(f"{len(shortcuts)} raccourcis Chrome trouvés", "INFO")

    all_configured = True
    for sc in shortcuts:
        status = "✅ CDP actif" if sc["has_cdp"] else "❌ CDP manquant"
        log(f"  {status} — {sc['path'].name} ({sc['path'].parent.name}/)", "INFO")
        if not sc["has_cdp"]:
            all_configured = False

    return all_configured, active


def apply_cdp(shortcuts, silent=False):
    """Ajoute CDP_FLAG aux raccourcis qui ne l'ont pas encore."""
    to_modify = [sc for sc in shortcuts if not sc["has_cdp"]]

    if not to_modify:
        log("Tous les raccourcis ont déjà le flag CDP ✅", "OK")
        return True

    log(f"{len(to_modify)} raccourcis à modifier :", "STEP")
    for sc in to_modify:
        log(f"  {sc['path']}", "INFO")
        log(f"    Avant : {sc['args'] or '(vide)'}", "INFO")
        log(f"    Après : {(sc['args'] + ' ' + CDP_FLAG).strip()}", "INFO")

    if not silent:
        confirm = input("\nAppliquer ces modifications ? [o/N] ").strip().lower()
        if confirm not in ("o", "oui", "y", "yes"):
            log("Annulé", "WARN")
            return False

    success = 0
    for sc in to_modify:
        new_args = (sc["args"] + " " + CDP_FLAG).strip()
        ok = write_shortcut(sc["path"], sc["target"], new_args)
        if ok:
            log(f"  ✅ Modifié : {sc['path'].name}", "OK")
            success += 1
        else:
            log(f"  ❌ Échec   : {sc['path'].name}", "ERR")

    log(f"\n{success}/{len(to_modify)} raccourcis mis à jour", "OK" if success == len(to_modify) else "WARN")

    if success > 0:
        log("", "INFO")
        log("IMPORTANT : Fermer et rouvrir Chrome pour activer le CDP", "WARN")
        log("Après relance Chrome, le pipeline fonctionne en autonomie totale ✅", "OK")

    return success > 0


def undo_cdp(shortcuts, silent=False):
    """Retire CDP_FLAG des raccourcis."""
    to_modify = [sc for sc in shortcuts if sc["has_cdp"]]

    if not to_modify:
        log("Aucun raccourci avec le flag CDP", "INFO")
        return True

    log(f"Suppression CDP de {len(to_modify)} raccourcis :", "STEP")
    for sc in to_modify:
        log(f"  {sc['path'].name}", "INFO")

    if not silent:
        confirm = input("\nSupprimerle flag CDP ? [o/N] ").strip().lower()
        if confirm not in ("o", "oui", "y", "yes"):
            log("Annulé", "WARN")
            return False

    for sc in to_modify:
        new_args = sc["args"].replace(CDP_FLAG, "").strip()
        ok = write_shortcut(sc["path"], sc["target"], new_args)
        log(f"  {'✅' if ok else '❌'} {sc['path'].name}", "OK" if ok else "ERR")

    return True


def verify_after_setup():
    """Vérifie que le setup fonctionne en lançant Chrome et testant nlm login."""
    log("Test de vérification post-setup", "STEP")

    chrome_exe = get_chrome_exe()
    if not chrome_exe:
        log("Chrome introuvable pour test", "WARN")
        return False

    log("Lancement Chrome de test...", "INFO")
    proc = subprocess.Popen(
        [chrome_exe,
         f"--remote-debugging-port={CDP_PORT}",
         "--no-first-run", "--no-default-browser-check",
         "--window-position=-32000,-32000", "--window-size=1,1",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    import socket, time
    for i in range(10):
        time.sleep(1)
        try:
            s = socket.create_connection(("127.0.0.1", CDP_PORT), timeout=1)
            s.close()
            log(f"CDP actif après {i+1}s", "OK")
            break
        except:
            pass
    else:
        proc.terminate()
        log("CDP non disponible — test échoué", "ERR")
        return False

    # Tester nlm login
    r = subprocess.run(
        ["nlm", "login", "--cdp-url", f"http://127.0.0.1:{CDP_PORT}", "--force"],
        capture_output=True, text=True, encoding="utf-8", timeout=30
    )
    proc.terminate()

    if r.returncode == 0:
        import re
        account = re.search(r"Account:\s+(.+)", r.stdout)
        log(f"NLM auth OK — {account.group(1) if account else '?'}", "OK")
        log("Setup validé ✅ — Pipeline autonome activé !", "OK")
        return True
    else:
        log(f"NLM auth échoué : {r.stderr[:80]}", "ERR")
        return False


# ─── POINT D'ENTRÉE ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Configuration Chrome CDP pour NLM Pipeline v2"
    )
    p.add_argument("--check",  action="store_true", help="Vérifie l'état sans modifier")
    p.add_argument("--silent", action="store_true", help="Applique sans confirmation")
    p.add_argument("--undo",   action="store_true", help="Supprime le flag CDP")
    p.add_argument("--verify", action="store_true", help="Vérifie après setup")
    args = p.parse_args()

    print("═" * 60)
    print("  Setup Chrome CDP — NLM Pipeline v2")
    print("  Christian Levannier — 04 juin 2026")
    print("═" * 60)

    shortcuts = find_chrome_shortcuts()
    log(f"Chrome trouvé : {get_chrome_exe()}", "OK" if get_chrome_exe() else "ERR")
    log(f"Raccourcis détectés : {len(shortcuts)}", "INFO")

    if args.check:
        check_cdp_status()
        sys.exit(0)

    if args.undo:
        undo_cdp(shortcuts, args.silent)
        sys.exit(0)

    # Mode normal : appliquer CDP
    log("", "INFO")
    log("Ce script ajoute --remote-debugging-port=9222 aux raccourcis Chrome.", "INFO")
    log("Résultat : le pipeline NLM s'authentifie automatiquement dès que", "INFO")
    log("Chrome est ouvert, sans aucune intervention manuelle.", "INFO")
    log("", "INFO")

    all_ok, cdp_active = check_cdp_status()

    if all_ok:
        log("Tous les raccourcis sont déjà configurés ✅", "OK")
        if not cdp_active:
            log("Relancez Chrome pour activer le CDP", "WARN")
    else:
        apply_cdp(shortcuts, args.silent)

    if args.verify:
        verify_after_setup()

    print("\n" + "═" * 60)
    print("  Pour vérifier : python setup_chrome_cdp.py --check")
    print("  Pour tester   : python setup_chrome_cdp.py --verify")
    print("═" * 60)
