#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NotebookLM Auto-Infographer - Script Python de secours
pipeline_runner.py - v1.0 - Christian Levannier - 31 mai 2026

Execution autonome du pipeline sans Claude Desktop.
Utilise le CLI `nlm` pour toutes les operations NotebookLM.

Usage :
  python pipeline_runner.py                    # config par defaut
  python pipeline_runner.py --config path.json # config custom
  python pipeline_runner.py --notebook "Rakuten" --download-only
  python pipeline_runner.py --dry-run          # simulation
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION PAR DÉFAUT (utilisée si pipeline_config.json absent)
# ══════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "notebook": {
        "name": "Affaire Rakuten",
        "match_mode": "contains"
    },
    "analysis": {
        "enabled": True,
        "query": "Quels sont les points clés, la chronologie, les parties impliquées, les enjeux et l'état actuel ?",
        "include_notes": True
    },
    "infographic": {
        "style": "auto_select",
        "orientation": "landscape",
        "detail_level": "detailed",
        "language": "fr",
        "focus_prompt": "Synthèse visuelle complète : faits clés, chronologie, parties impliquées, enjeux, état actuel",
        "title_pattern": "{date} — {notebook_name} — Synthèse"
    },
    "output": {
        "folder": os.path.join(os.environ.get("APPDATA", ""), "Claude", "pipelines", "notebooklm-infographer", "outputs"),
        "filename_pattern": "{date}_{notebook_slug}_{orientation}_Infographie.png",
        "overwrite_if_exists": False,
        "keep_last_n": 10
    },
    "notifications": {
        "enabled": True,
        "log_file": os.path.join(os.environ.get("APPDATA", ""), "Claude", "pipelines", "notebooklm-infographer", "logs", "pipeline_log.json")
    },
    "retry": {"max_attempts": 3, "wait_seconds_between": 30},
    "polling": {"interval_seconds": 20, "max_wait_seconds": 180}
}

# Chemin par défaut du fichier de config
DEFAULT_CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA", ""),
    "Claude", "pipelines", "notebooklm-infographer", "pipeline_config.json"
)


# ══════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════

class Colors:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "[i]", "OK": "[OK]", "WARN": "[!] ", "ERR": "[X]", "STEP": ">>>"}
    colors = {"INFO": Colors.CYAN, "OK": Colors.GREEN, "WARN": Colors.YELLOW,
              "ERR": Colors.RED, "STEP": Colors.BOLD}
    icon  = icons.get(level, "·")
    color = colors.get(level, "")
    print(f"{color}[{ts}] {icon}  {msg}{Colors.RESET}")

def slugify(text):
    """Convertit un titre en slug URL-safe."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text

def run_nlm(args, capture=True, timeout=120):
    """Exécute une commande nlm et retourne (returncode, stdout, stderr)."""
    cmd = ["nlm"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=capture, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout après {timeout}s"
    except FileNotFoundError:
        return -2, "", "nlm CLI introuvable — vérifiez l'installation"

def notify_windows(title, message):
    """Notification Windows via PowerShell."""
    script = (
        f"Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.MessageBox]::Show('{message}', '{title}')"
    )
    subprocess.Popen(
        ["powershell", "-Command", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


# ══════════════════════════════════════════════════════════════════════
# PHASES DU PIPELINE
# ══════════════════════════════════════════════════════════════════════

def phase0_load_config(config_path):
    """Phase 0 : Lire pipeline_config.json."""
    log("Phase 0 — Lecture de la configuration", "STEP")

    config = DEFAULT_CONFIG.copy()

    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                user_config = json.load(f)
            # Merge profond
            for key in user_config:
                if key.startswith("_"):
                    continue
                if isinstance(user_config[key], dict) and key in config:
                    config[key].update({k: v for k, v in user_config[key].items() if not k.startswith("_")})
                else:
                    config[key] = user_config[key]
            log(f"Config chargée : {config_path}", "OK")
        except Exception as e:
            log(f"Erreur lecture config : {e} — valeurs par défaut utilisées", "WARN")
    else:
        log(f"Config absente ({config_path}) — valeurs par défaut utilisées", "WARN")

    # Créer les dossiers si nécessaire
    for folder_key in ["folder"]:
        folder = config["output"].get(folder_key, "")
        if folder:
            Path(folder).mkdir(parents=True, exist_ok=True)

    log_dir = Path(config["notifications"]["log_file"]).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    log(f"  notebook    : {config['notebook']['name']}", "INFO")
    log(f"  orientation : {config['infographic']['orientation']}", "INFO")
    log(f"  dossier     : {config['output']['folder']}", "INFO")

    return config


def phase1_find_notebook(config):
    """Phase 1 : Identifier le notebook cible."""
    log("Phase 1 — Identification du notebook", "STEP")

    code, out, err = run_nlm(["notebook", "list", "--json"])
    if code != 0:
        log(f"Erreur nlm notebook list : {err}", "ERR")
        return None, None, None

    try:
        notebooks = json.loads(out)
    except json.JSONDecodeError:
        log(f"Réponse nlm non-JSON : {out[:200]}", "ERR")
        return None, None, None

    name_filter = config["notebook"]["name"].lower()
    match_mode  = config["notebook"].get("match_mode", "contains")

    matches = []
    for nb in notebooks:
        title = nb.get("title", "")
        tl    = title.lower()
        if match_mode == "exact"       and tl == name_filter:
            matches.append(nb)
        elif match_mode == "contains"  and name_filter in tl:
            matches.append(nb)
        elif match_mode == "starts_with" and tl.startswith(name_filter):
            matches.append(nb)

    if not matches:
        log(f"Notebook '{config['notebook']['name']}' introuvable (mode: {match_mode})", "ERR")
        log(f"Notebooks disponibles : {[nb.get('title','?') for nb in notebooks[:5]]}", "INFO")
        return None, None, None

    # Prendre le plus récemment modifié
    best = sorted(matches, key=lambda x: x.get("modified_at", ""), reverse=True)[0]
    nb_id    = best.get("id") or best.get("notebook_id", "")
    nb_title = best.get("title", "")
    nb_srcs  = best.get("source_count", 0)

    log(f"Notebook trouvé : {nb_title} ({nb_srcs} sources)", "OK")
    return nb_id, nb_title, nb_srcs


def phase2_analyze(config, nb_id):
    """Phase 2 : Analyser le contenu et enrichir le focus_prompt."""
    if not config["analysis"].get("enabled", True):
        log("Phase 2 — Analyse désactivée (analysis.enabled=false)", "INFO")
        return config["infographic"]["focus_prompt"]

    log("Phase 2 — Analyse du contenu", "STEP")

    query = config["analysis"]["query"]
    code, out, err = run_nlm(
        ["notebook", "query", nb_id, query, "--json"],
        timeout=180
    )

    if code != 0:
        log(f"Erreur analyse (non bloquant) : {err[:100]}", "WARN")
        return config["infographic"]["focus_prompt"]

    try:
        data   = json.loads(out)
        answer = data.get("answer") or data.get("response") or data.get("text", "")
        if answer:
            enriched = config["infographic"]["focus_prompt"] + "\n\nPoints clés identifiés : " + answer[:500]
            log(f"Focus_prompt enrichi ({len(answer)} chars)", "OK")
            return enriched
    except Exception:
        pass

    log("Analyse OK (réponse non parsée — focus_prompt non modifié)", "WARN")
    return config["infographic"]["focus_prompt"]


def phase3_check_existing_or_trigger(config, nb_id, nb_title, dry_run=False):
    """Phase 3 : Vérifier s'il y a un artifact récent ou signaler qu'une génération est nécessaire."""
    log("Phase 3 — Vérification des artifacts existants", "STEP")

    code, out, err = run_nlm(["studio", "status", nb_id, "--json"])
    if code != 0:
        log(f"Erreur studio status : {err[:100]}", "WARN")
        return None

    try:
        data      = json.loads(out)
        artifacts = data if isinstance(data, list) else data.get("artifacts", [])
    except Exception:
        artifacts = []

    # Chercher la dernière infographie complète
    infographics = [
        a for a in artifacts
        if a.get("type") == "infographic" and a.get("status") == "completed"
    ]

    if infographics:
        latest = sorted(infographics, key=lambda x: x.get("created_at", ""), reverse=True)[0]
        art_id = latest.get("artifact_id", "")
        art_title = latest.get("title", "")
        art_date  = latest.get("created_at", "")[:10]
        log(f"Infographie existante : '{art_title}' ({art_date})", "OK")

        if dry_run:
            log("[DRY-RUN] Téléchargement simulé — artifact_id : " + art_id, "INFO")
            return art_id

        return art_id
    else:
        log("Aucune infographie disponible dans le Studio.", "WARN")
        log("→ Pour en générer une : ouvrir Claude Desktop et dire :", "INFO")
        log(f"  'Génère une infographie pour le notebook {nb_title}'", "INFO")
        log("→ Puis relancer ce script pour télécharger.", "INFO")
        return None


def phase4_wait_for_completion(config, nb_id, artifact_id):
    """Phase 4 : Polling jusqu'à complétion (si artifact en cours)."""
    # Dans le mode fallback, on travaille uniquement avec des artifacts déjà terminés
    # Cette phase est un no-op mais reste pour compatibilité future
    log("Phase 4 — Artifact déjà complété (pas de polling nécessaire)", "OK")
    return True


def phase5_build_filename(config, nb_title):
    """Phase 5 : Construire le nom de fichier de sortie."""
    log("Phase 5 — Construction du nom de fichier", "STEP")

    today = datetime.now().strftime("%Y-%m-%d")
    now   = datetime.now().strftime("%Hh%M")
    slug  = slugify(nb_title)
    ori   = config["infographic"]["orientation"]
    style = config["infographic"]["style"]

    pattern  = config["output"]["filename_pattern"]
    filename = (pattern
        .replace("{date}", today)
        .replace("{time}", now)
        .replace("{notebook_name}", nb_title)
        .replace("{notebook_slug}", slug)
        .replace("{orientation}", ori)
        .replace("{style}", style)
    )

    output_folder = config["output"]["folder"]
    output_path   = os.path.join(output_folder, filename)

    # Gestion overwrite
    if os.path.exists(output_path) and not config["output"].get("overwrite_if_exists", False):
        base, ext = os.path.splitext(output_path)
        i = 2
        while os.path.exists(f"{base}_v{i}{ext}"):
            i += 1
        output_path = f"{base}_v{i}{ext}"
        log(f"Fichier existant → renommé en v{i}", "INFO")

    log(f"Nom de fichier : {os.path.basename(output_path)}", "OK")
    return output_path


def phase6_download(config, nb_id, artifact_id, output_path, dry_run=False):
    """Phase 6 : Télécharger l'infographie."""
    log("Phase 6 — Téléchargement de l'infographie", "STEP")

    if dry_run:
        log(f"[DRY-RUN] Simulation téléchargement → {output_path}", "INFO")
        return True

    # Créer dossier si nécessaire
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["download", "infographic", nb_id, "--output", output_path, "--no-progress"]
    if artifact_id:
        cmd += ["--id", artifact_id]

    code, out, err = run_nlm(cmd, timeout=120)

    if code != 0:
        log(f"Erreur téléchargement : {err[:200]}", "ERR")
        return False

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        size_kb = os.path.getsize(output_path) // 1024
        log(f"Fichier sauvegardé : {os.path.basename(output_path)} ({size_kb} KB)", "OK")
        return True
    else:
        log("Fichier absent ou vide après téléchargement", "ERR")
        return False


def phase7_log_and_report(config, nb_title, nb_srcs, artifact_id, output_path,
                           success, duration, error_msg=""):
    """Phase 7 : Journaliser et afficher le rapport final."""
    log("Phase 7 — Rapport et journalisation", "STEP")

    entry = {
        "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status":           "success" if success else "failure",
        "notebook":         nb_title or "?",
        "source_count":     nb_srcs or 0,
        "artifact_id":      artifact_id or "",
        "file":             output_path or "",
        "duration_seconds": round(duration),
        "runner":           "pipeline_runner.py"
    }
    if error_msg:
        entry["error"] = error_msg

    # Lire/créer le log JSON
    log_file = config["notifications"]["log_file"]
    try:
        if os.path.exists(log_file):
            with open(log_file, encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = []
        logs.append(entry)
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Erreur écriture log : {e}", "WARN")

    # Nettoyage archives (keep_last_n)
    keep_n = config["output"].get("keep_last_n", 0)
    if keep_n > 0 and success:
        folder = config["output"]["folder"]
        try:
            pngs = sorted(
                [f for f in Path(folder).glob("*.png")],
                key=lambda x: x.stat().st_mtime, reverse=True
            )
            for old in pngs[keep_n:]:
                old.unlink()
                log(f"Archive supprimée : {old.name}", "INFO")
        except Exception:
            pass

    # Rapport console
    sep = "-" * 48
    print(f"\n{Colors.BOLD}{sep}{Colors.RESET}")
    if success:
        print(f"{Colors.GREEN}{Colors.BOLD}[OK] PIPELINE TERMINE{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}[X]  PIPELINE ECHOUE{Colors.RESET}")
    print(f"  Notebook   : {nb_title or '?'}")
    print(f"  Sources    : {nb_srcs or '?'}")
    print(f"  Duree      : {round(duration)}s")
    if success and output_path:
        print(f"  Fichier    : {os.path.basename(output_path)}")
        print(f"  Dossier    : {config['output']['folder']}")
    elif error_msg:
        print(f"  Erreur     : {error_msg}")
    print(f"{Colors.BOLD}{sep}{Colors.RESET}\n")

    # Notification Windows
    if config["notifications"].get("enabled", True) and success:
        try:
            notify_windows(
                "Pipeline NotebookLM ✅",
                f"Infographie générée : {os.path.basename(output_path or '')}"
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

def run_pipeline(config_path, notebook_override=None, download_only=False, dry_run=False):
    start = time.time()
    error_msg = ""

    print(f"\n{Colors.BOLD}{'='*48}")
    print("  NotebookLM Auto-Infographer - Pipeline Runner")
    print(f"  v1.0 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*48}{Colors.RESET}\n")

    # Vérifier que nlm est installé
    if not shutil.which("nlm"):
        log("nlm CLI introuvable. Installez-le : pip install notebooklm-tools", "ERR")
        sys.exit(1)

    # ── Phase 0 : Config
    config = phase0_load_config(config_path)
    if notebook_override:
        config["notebook"]["name"] = notebook_override
        log(f"Override notebook : {notebook_override}", "INFO")

    nb_id = nb_title = nb_srcs = artifact_id = output_path = None

    try:
        # ── Phase 1 : Trouver le notebook
        nb_id, nb_title, nb_srcs = phase1_find_notebook(config)
        if not nb_id:
            raise RuntimeError(f"Notebook '{config['notebook']['name']}' introuvable")

        # ── Phase 2 : Analyser (sauf download-only)
        focus_prompt = config["infographic"]["focus_prompt"]
        if not download_only:
            focus_prompt = phase2_analyze(config, nb_id)

        # ── Phase 3 : Trouver artifact existant
        artifact_id = phase3_check_existing_or_trigger(config, nb_id, nb_title, dry_run)
        if not artifact_id:
            raise RuntimeError(
                "Aucune infographie disponible. "
                "Générez-en une via Claude Desktop, puis relancez ce script."
            )

        # ── Phase 4 : Vérification complétion (no-op en mode fallback)
        phase4_wait_for_completion(config, nb_id, artifact_id)

        # ── Phase 5 : Nom de fichier
        output_path = phase5_build_filename(config, nb_title)

        # ── Phase 6 : Téléchargement
        success = phase6_download(config, nb_id, artifact_id, output_path, dry_run)
        if not success:
            raise RuntimeError("Échec du téléchargement")

    except RuntimeError as e:
        error_msg = str(e)
        log(error_msg, "ERR")
        success = False

    except KeyboardInterrupt:
        log("Interrompu par l'utilisateur", "WARN")
        success = False
        error_msg = "Interrompu"

    # ── Phase 7 : Log + rapport
    duration = time.time() - start
    phase7_log_and_report(config, nb_title, nb_srcs, artifact_id,
                          output_path, success, duration, error_msg)

    return 0 if success else 1


# ══════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="NotebookLM Auto-Infographer — Script de secours autonome",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python pipeline_runner.py
  python pipeline_runner.py --config C:/mon/dossier/pipeline_config.json
  python pipeline_runner.py --notebook "Affaire Rakuten"
  python pipeline_runner.py --download-only
  python pipeline_runner.py --dry-run
        """
    )
    parser.add_argument(
        "--config", "-c",
        default=DEFAULT_CONFIG_PATH,
        help=f"Chemin du fichier de configuration (défaut : {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument(
        "--notebook", "-n",
        default=None,
        help="Override du nom de notebook (priorité sur la config)"
    )
    parser.add_argument(
        "--download-only", "-d",
        action="store_true",
        help="Télécharger uniquement (sans analyse)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulation complète sans téléchargement réel"
    )

    args = parser.parse_args()
    sys.exit(run_pipeline(
        config_path=args.config,
        notebook_override=args.notebook,
        download_only=args.download_only,
        dry_run=args.dry_run
    ))
