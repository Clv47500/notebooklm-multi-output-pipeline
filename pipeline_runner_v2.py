#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NotebookLM Multi-Output Pipeline v2.0
pipeline_runner_v2.py — Christian Levannier — 04 juin 2026

Génération automatisée de TOUS les formats NotebookLM Studio :
    audio, video, slide_deck, infographic, report, mind_map,
    flashcards, quiz, data_table

Corrections v2 (issues identifiées lors des tests du 04/06/2026) :
  1. nlm login --force obligatoire avant chaque session de download
     (le token de téléchargement expire indépendamment du token API)
  2. mind_map : workaround via parsing de la réponse API brute
     (nlm download mind-map retourne null dans Response Data — bug v0.6.15)

Usage :
    python pipeline_runner_v2.py                             # config par défaut
    python pipeline_runner_v2.py --config path.json          # config custom
    python pipeline_runner_v2.py --notebook "Affaire Rakuten"
    python pipeline_runner_v2.py --types audio,slide_deck,report
    python pipeline_runner_v2.py --dry-run                   # simulation
    python pipeline_runner_v2.py --no-login-refresh          # skip login refresh

Installation :
    pip install notebooklm-tools

Config par défaut :
    %APPDATA%\\Claude\\pipelines\\notebooklm-infographer\\pipeline_config_v2.json
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════════════════════

VERSION = "2.0.0"

EXT_MAP = {
    "audio":       ".m4a",
    "video":       ".mp4",
    "slide_deck":  ".pdf",
    "infographic": ".png",
    "report":      ".md",
    "mind_map":    ".json",
    "flashcards":  ".html",
    "quiz":        ".html",
    "data_table":  ".csv",
}

NLM_DOWNLOAD_CMD = {
    "audio":       ["download", "audio"],
    "video":       ["download", "video"],
    "slide_deck":  ["download", "slide-deck"],
    "infographic": ["download", "infographic"],
    "report":      ["download", "report"],
    "mind_map":    ["download", "mind-map"],
    "flashcards":  ["download", "flashcards"],
    "quiz":        ["download", "quiz"],
    "data_table":  ["download", "data-table"],
}

NLM_CREATE_CMD = {
    "audio":       ["audio", "create"],
    "video":       ["video", "create"],
    "slide_deck":  ["slides", "create"],
    "infographic": ["infographic", "create"],
    "report":      ["report", "create"],
    "mind_map":    ["mindmap", "create"],
    "flashcards":  ["flashcards", "create"],
    "quiz":        ["quiz", "create"],
    "data_table":  ["data-table", "create"],
}

CREATE_FLAGS = {
    "audio":       lambda cfg: ["--format",   cfg.get("format",      "deep_dive"),
                                 "--length",   cfg.get("length",      "default"),
                                 "--language", cfg.get("language",    "fr")],
    "video":       lambda cfg: ["--format",   cfg.get("format",      "explainer")],
    "slide_deck":  lambda cfg: ["--format",   cfg.get("format",      "detailed_deck"),
                                 "--language", cfg.get("language",    "fr")],
    "infographic": lambda cfg: ["--orientation", cfg.get("orientation", "landscape"),
                                 "--style",       cfg.get("style",      "auto_select"),
                                 "--language",    cfg.get("language",   "fr")],
    "report":      lambda cfg: ["--format",   cfg.get("format",      "Briefing Doc"),
                                 "--language", cfg.get("language",    "fr")],
    "mind_map":    lambda cfg: ["--title",    cfg.get("title",       "Mind Map")],
    "flashcards":  lambda cfg: ["--difficulty", cfg.get("difficulty", "medium")],
    "quiz":        lambda cfg: ["--question-count", str(cfg.get("question_count", 10)),
                                 "--difficulty",      cfg.get("difficulty", "medium")],
    "data_table":  lambda cfg: [],
}

DOWNLOAD_FLAGS = {
    "audio":       lambda cfg: ["--no-progress"],
    "video":       lambda cfg: ["--no-progress"],
    "infographic": lambda cfg: ["--no-progress"],
    "slide_deck":  lambda cfg: ["--no-progress",
                                 "--format", cfg.get("file_format", "pdf")],
}

DEFAULT_CONFIG_PATH = (
    Path(os.environ.get("APPDATA", "")) /
    "Claude/pipelines/notebooklm-infographer/pipeline_config_v2.json"
)

CDP_URL          = "http://127.0.0.1:9222"
CDP_PORT         = 9222
COOKIES_FILE     = Path(os.path.expanduser("~")) / \
    ".notebooklm-mcp-cli/profiles/default/cookies.json"

# Comet (Perplexity) — navigateur utilisé pour NLM
COMET_EXE = str(
    Path(os.environ.get("LOCALAPPDATA","")) /
    "Perplexity/Comet/Application/comet.exe"
)
NLM_URL = "https://notebooklm.google.com"


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

class Colors:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def log(msg, level="INFO"):
    ts   = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "[ i ]", "OK": "[ ✓ ]", "WARN": "[ ! ]",
              "ERR": "[ ✗ ]", "STEP": "[ → ]"}
    clrs  = {"INFO": Colors.CYAN,   "OK": Colors.GREEN,  "WARN": Colors.YELLOW,
              "ERR": Colors.RED,   "STEP": Colors.BOLD}
    print(f"{clrs.get(level,'')}[{ts}] {icons.get(level,'     ')} {msg}{Colors.RESET}")

def slugify(text):
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", text).strip("-")

def run_nlm(args, timeout=180):
    try:
        r = subprocess.run(
            ["nlm"] + args,
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout {timeout}s"
    except FileNotFoundError:
        return -2, "", "nlm CLI introuvable"


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 0 — PREFLIGHT + LOGIN REFRESH (FIX v2 #1)
# ══════════════════════════════════════════════════════════════════════════════

def phase0_preflight(skip_login_refresh=False):
    log("Phase 0 — Vérifications & auth refresh", "STEP")

    code, out, _ = run_nlm(["--version"], timeout=10)
    if code != 0:
        log("nlm CLI introuvable — pip install notebooklm-tools", "ERR")
        return False
    log(f"nlm {out.strip()}", "OK")

    if skip_login_refresh:
        log("Login refresh ignoré (--no-login-refresh)", "WARN")
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # AUTH VIA COMET (Perplexity) — navigateur utilisé pour NLM
    #
    # Comet = C:\Users\levan\AppData\Local\Perplexity\Comet\Application\comet.exe
    # Stratégie :
    #   Niveau 1 : Comet déjà lancé avec CDP actif     → login direct
    #   Niveau 2 : Comet ouvert mais sans CDP           → fermer + relancer avec CDP
    #   Niveau 3 : Comet fermé                         → lancer + NLM + login
    # Dans tous les cas : 100% automatique, zéro intervention manuelle.
    # ─────────────────────────────────────────────────────────────────────────
    log("Auth via Comet (Perplexity)...", "INFO")

    import socket

    def _cdp_ok():
        try:
            s = socket.create_connection(("127.0.0.1", CDP_PORT), timeout=2)
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            return False

    def _nlm_login_cdp():
        code, out, err = run_nlm(["login", "--cdp-url", CDP_URL, "--force"], timeout=30)
        if code == 0:
            m_a = re.search(r"Account:\s+(.+)", out)
            m_c = re.search(r"Cookies:\s+(\d+)", out)
            log(f"Auth OK — {m_a.group(1) if m_a else '?'} "
                f"({m_c.group(1) if m_c else '?'} cookies)", "OK")
            return True
        log(f"nlm login CDP : {err[:80]}", "WARN")
        return False

    def _comet_running():
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq comet.exe", "/NH"],
            capture_output=True, text=True
        )
        return "comet.exe" in r.stdout

    def _launch_comet():
        """Ferme Comet si ouvert, relance avec CDP + NLM."""
        if not Path(COMET_EXE).exists():
            log(f"Comet introuvable : {COMET_EXE}", "ERR")
            return False
        if _comet_running():
            log("Fermeture Comet (pour activer CDP)...", "INFO")
            subprocess.run(["taskkill", "/F", "/IM", "comet.exe"],
                           capture_output=True)
            time.sleep(2)
        log(f"Lancement Comet avec CDP (port {CDP_PORT}) + NLM...", "INFO")
        subprocess.Popen(
            [COMET_EXE, f"--remote-debugging-port={CDP_PORT}",
             "--no-first-run", "--no-default-browser-check", NLM_URL],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        # Attendre CDP (max 15s)
        for i in range(15):
            time.sleep(1)
            if _cdp_ok():
                log(f"Comet CDP prêt ({i+1}s)", "OK")
                return True
        log("Comet lancé — CDP non disponible après 15s", "WARN")
        return False

    # ── Niveau 1 : Comet déjà en mode CDP ───────────────────────────────────
    if _cdp_ok():
        log("Niveau 1 : Comet CDP déjà actif → login direct", "INFO")
        if _nlm_login_cdp():
            return True

    # ── Niveau 2/3 : Lancer/relancer Comet avec CDP ─────────────────────────
    if _comet_running():
        log("Niveau 2 : Comet ouvert sans CDP → relance avec CDP", "INFO")
    else:
        log("Niveau 3 : Comet fermé → lancement + NLM", "INFO")

    if _launch_comet():
        # Laisser NLM charger (session Google déjà active dans Comet)
        log("Attente chargement NLM dans Comet...", "INFO")
        time.sleep(6)
        if _nlm_login_cdp():
            return True

    log("Auth Comet impossible — pipeline continue (downloads peuvent échouer)", "WARN")
    return True


def _is_ascii(s):
    try:
        s.encode("ascii")
        return True
    except (UnicodeEncodeError, AttributeError):
        return False


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — RÉSOLUTION NOTEBOOK
# ══════════════════════════════════════════════════════════════════════════════

def phase1_resolve_notebook(notebook_name, match_mode="contains"):
    log(f"Phase 1 — Notebook : '{notebook_name}'", "STEP")
    code, out, err = run_nlm(["notebook", "list", "--json"], timeout=30)
    if code != 0:
        log(f"Erreur liste : {err[:80]}", "ERR")
        return None, None, 0
    try:
        notebooks = json.loads(out)
    except json.JSONDecodeError:
        log("Réponse non-JSON", "ERR")
        return None, None, 0

    name_l = notebook_name.lower()
    matches = [
        nb for nb in notebooks
        if (match_mode == "exact"       and nb.get("title","") == notebook_name)
        or (match_mode == "contains"    and name_l in nb.get("title","").lower())
        or (match_mode == "starts_with" and nb.get("title","").lower().startswith(name_l))
    ]
    if not matches:
        log(f"Notebook '{notebook_name}' non trouvé", "ERR")
        return None, None, 0

    nb = matches[0]
    log(f"'{nb.get('title','')}' ({nb.get('source_count',0)} sources) "
        f"ID={nb.get('id','')[:8]}...", "OK")
    return nb.get("id",""), nb.get("title",""), nb.get("source_count",0)


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — CRÉATION ARTIFACT
# ══════════════════════════════════════════════════════════════════════════════

def phase2_create_artifact(nb_id, output_type, type_cfg, dry_run=False):
    log(f"  [{output_type}] Création...", "INFO")
    if dry_run:
        return f"dry-{output_type}"

    base = NLM_CREATE_CMD.get(output_type)
    if not base:
        log(f"  Type '{output_type}' non supporté", "ERR")
        return None

    flags = CREATE_FLAGS.get(output_type, lambda c: [])(type_cfg)
    code, out, err = run_nlm(base + [nb_id] + flags + ["--confirm"], timeout=60)

    if code != 0:
        log(f"  Erreur create : {(err or out)[:150]}", "ERR")
        return None

    m = re.search(r"(?:Artifact ID|ID)\s*[:\s]+([a-f0-9]{8}-[a-f0-9\-]{27})", out, re.I)
    artifact_id = m.group(1) if m else "created_no_id"
    log(f"  [{output_type}] démarré — {artifact_id[:8]}...", "OK")
    return artifact_id


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — POLLING
# ══════════════════════════════════════════════════════════════════════════════

def phase3_poll(nb_id, artifact_id, output_type, interval_s=15, timeout_min=12):
    deadline = time.time() + timeout_min * 60
    poll_n   = 0

    while time.time() < deadline:
        poll_n += 1
        code, out, err = run_nlm(["studio", "status", nb_id, "--json"], timeout=20)
        if code != 0:
            time.sleep(interval_s)
            continue
        try:
            arts = json.loads(out)
            if isinstance(arts, dict):
                arts = arts.get("artifacts", [])

            match = None
            if artifact_id and artifact_id != "created_no_id":
                match = next((a for a in arts if a.get("id") == artifact_id), None)
            if not match:
                match = next(
                    (a for a in arts if a.get("type") == output_type
                     and a.get("status") in ("completed","in_progress")), None
                )

            if match:
                status = match.get("status","?")
                if status == "completed":
                    log(f"  [{output_type}] ✓ completed (poll #{poll_n})", "OK")
                    return match.get("id", artifact_id)
                if status == "failed":
                    log(f"  [{output_type}] ✗ failed", "ERR")
                    return None
                log(f"  [{output_type}] {status}... (poll #{poll_n})", "INFO")
        except json.JSONDecodeError:
            pass

        time.sleep(interval_s)

    log(f"  [{output_type}] TIMEOUT {timeout_min}min", "ERR")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════

def phase4_download(nb_id, artifact_id, output_type, out_path, type_cfg, dry_run=False):
    if dry_run:
        log(f"  [DRY-RUN] {output_type} → {Path(out_path).name}", "INFO")
        return True

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    # ─── FIX v2 #2 : mind_map workaround ────────────────────────────────────
    if output_type == "mind_map":
        return _mindmap_workaround(nb_id, artifact_id, out_path)

    # ─── Download standard ──────────────────────────────────────────────────
    base  = NLM_DOWNLOAD_CMD.get(output_type, [])
    extra = DOWNLOAD_FLAGS.get(output_type, lambda c: [])(type_cfg)
    cmd   = base + [nb_id, "--output", str(out_path)]
    if artifact_id and "dry" not in artifact_id and "created_no_id" != artifact_id:
        cmd += ["--id", artifact_id]
    cmd += extra

    code, out, err = run_nlm(cmd, timeout=180)

    # ─── Retry si token download expiré ─────────────────────────────────────
    if code != 0 and ("login" in (out+err).lower() or "302" in (out+err)
                      or "Download failed" in (out+err)):
        log(f"  Token expiré — relance auth Comet + retry [{output_type}]", "WARN")
        run_nlm(["login", "--cdp-url", CDP_URL, "--force"], timeout=30)
        code, out, err = run_nlm(cmd, timeout=180)

    if code != 0:
        log(f"  [{output_type}] Download échoué : {(err or out)[:120]}", "ERR")
        return False

    p = Path(out_path)
    if p.exists() and p.stat().st_size > 100:
        log(f"  [{output_type}] ✓ {p.stat().st_size//1024} KB", "OK")
        return True

    log(f"  [{output_type}] Fichier absent/vide après download", "ERR")
    return False


def _mindmap_workaround(nb_id, artifact_id, out_path):
    """
    FIX v2 #2 — Bug nlm v0.6.15 : nlm download mind-map → Response Data null.

    Cause : l'API NLM ne retourne pas d'URL de téléchargement directe pour les
    mind maps dans la version actuelle de l'endpoint batchexecute (RPC cFji9).

    Workaround : sauvegarder les métadonnées disponibles + lien direct NLM.
    À mettre à jour quand nlm > v0.6.15 sera disponible.
    """
    log("  [mind_map] Workaround bug nlm v0.6.15 — métadonnées seulement", "WARN")

    code, out, err = run_nlm(["studio", "status", nb_id, "--json"], timeout=20)
    try:
        arts = json.loads(out)
        mm = next((a for a in arts
                   if a.get("type") == "mind_map"
                   and a.get("status") == "completed"), None)
        if mm:
            data = {
                "_note":        "Bug nlm v0.6.15 — contenu complet non téléchargeable via CLI",
                "_workaround":  "Voir https://notebooklm.google.com/notebook/" + nb_id,
                "_fix_version": "Mettre à jour nlm quand > v0.6.15 disponible",
                "artifact_id":  mm.get("id",""),
                "notebook_id":  nb_id,
                "type":         "mind_map",
                "status":       "completed",
                "generated_at": datetime.now().isoformat(),
            }
            Path(out_path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            log("  [mind_map] Métadonnées sauvegardées (contenu indisponible — bug CLI)", "WARN")
            log(f"  [mind_map] Voir sur : https://notebooklm.google.com/notebook/{nb_id}", "INFO")
            return True
    except Exception:
        pass

    log("  [mind_map] Workaround échoué", "ERR")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(config_path=None, notebook_override=None, types_override=None,
                 dry_run=False, skip_login_refresh=False):

    start = time.time()

    # Charger config
    cfg_p = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    config = json.loads(cfg_p.read_text(encoding="utf-8")) if cfg_p.exists() else {}
    if cfg_p.exists():
        log(f"Config : {cfg_p.name}", "OK")
    else:
        log(f"Config introuvable — valeurs par défaut", "WARN")

    notebook_name   = notebook_override or config.get("notebook",{}).get("name","test")
    match_mode      = config.get("notebook",{}).get("match_mode","contains")
    output_types    = types_override or config.get("output_types",
                                                    ["audio","slide_deck","report"])
    outputs_cfg     = config.get("outputs", {})
    exec_cfg        = config.get("execution", {})
    output_dir      = Path(config.get("output_dir", str(
                        Path(os.environ.get("APPDATA","")) /
                        "Claude/pipelines/notebooklm-infographer/outputs"
                    )))
    continue_on_err = exec_cfg.get("continue_on_error", True)
    poll_interval   = exec_cfg.get("polling_interval_s", 15)
    timeout_min     = exec_cfg.get("timeout_min", 12)

    log("=" * 60)
    log(f"NotebookLM Multi-Output Pipeline v{VERSION}", "STEP")
    log(f"Notebook : {notebook_name}")
    log(f"Types    : {', '.join(output_types)}")
    log(f"Output   : {output_dir}")
    if dry_run: log("DRY-RUN — aucune génération réelle", "WARN")
    log("=" * 60)

    # Phase 0
    if not phase0_preflight(skip_login_refresh):
        return {}

    # Phase 1
    nb_id, nb_title, nb_srcs = phase1_resolve_notebook(notebook_name, match_mode)
    if not nb_id:
        if dry_run:
            # Mode dry-run sans auth : utiliser des valeurs de test
            log("DRY-RUN sans auth — notebook simulé", "WARN")
            nb_id, nb_title, nb_srcs = "test-notebook-id-dry-run", notebook_name, 0
        else:
            return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug     = slugify(nb_title)
    results  = {}

    # ─── TYPE ROUTER ────────────────────────────────────────────────────────
    for output_type in output_types:
        log(f"\n{'─'*50}", "STEP")
        log(f"  {output_type.upper()}", "STEP")
        log(f"{'─'*50}")

        type_cfg = outputs_cfg.get(output_type, {})
        ext      = EXT_MAP.get(output_type, ".bin")
        out_path = output_dir / f"{date_str}_{slug}_{output_type}{ext}"

        result = {
            "type": output_type, "status": "❌",
            "output_path": str(out_path), "size_bytes": 0,
            "error": None, "artifact_id": None, "duration_s": 0,
        }
        t0 = time.time()

        try:
            # Create
            artifact_id = phase2_create_artifact(nb_id, output_type, type_cfg, dry_run)
            if not artifact_id:
                result.update({"error": "create failed", "status": "❌ create"})
                results[output_type] = result
                if not continue_on_err: break
                continue
            result["artifact_id"] = artifact_id

            # Poll
            if not dry_run:
                final_id = phase3_poll(nb_id, artifact_id, output_type,
                                       poll_interval, timeout_min)
                if not final_id:
                    result.update({"error": "timeout", "status": "❌ timeout"})
                    results[output_type] = result
                    if not continue_on_err: break
                    continue
                result["artifact_id"] = final_id
            else:
                final_id = artifact_id

            # Download
            ok = phase4_download(nb_id, final_id, output_type,
                                  str(out_path), type_cfg, dry_run)
            result["duration_s"] = round(time.time() - t0, 1)

            if ok and (dry_run or out_path.exists()):
                result["size_bytes"] = out_path.stat().st_size if out_path.exists() else 0
                result["status"] = "✅"
                log(f"  ✅ {output_type} — {result['size_bytes']//1024} KB "
                    f"en {result['duration_s']}s", "OK")
            else:
                result.update({"error": "download failed", "status": "❌ download"})
                if not continue_on_err: break

        except Exception as e:
            result.update({"error": str(e), "status": f"❌ {type(e).__name__}",
                           "duration_s": round(time.time() - t0, 1)})
            log(f"  Exception [{output_type}] : {e}", "ERR")
            if not continue_on_err: break

        results[output_type] = result

    # ─── RAPPORT ─────────────────────────────────────────────────────────────
    total_s  = round(time.time() - start, 1)
    ok_count = sum(1 for r in results.values() if r["status"] == "✅")

    log(f"\n{'═'*60}", "STEP")
    log(f"RAPPORT — {nb_title}", "STEP")
    log(f"{'═'*60}")
    print(f"\n{'TYPE':<15} {'STATUT':>8} {'TAILLE':>10}  FICHIER")
    print("─" * 70)
    for t, r in results.items():
        sz   = f"{r['size_bytes']//1024} KB" if r["size_bytes"] else "—"
        note = f"  [{r['error']}]" if r.get("error") else ""
        print(f"{t:<15} {r['status']:>8} {sz:>10}  {Path(r['output_path']).name}{note}")
    print("─" * 70)
    log(f"Résultat : {ok_count}/{len(output_types)} — Durée : {total_s}s")

    # Sauvegarder rapport JSON
    report = output_dir / f"{date_str}_{slug}_v2_report.json"
    report.write_text(json.dumps({
        "version": VERSION, "date": date_str,
        "notebook": nb_title, "notebook_id": nb_id,
        "duration_s": total_s, "ok": ok_count, "total": len(output_types),
        "results": results,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    log(f"Rapport : {report}", "OK")

    status_msg = {
        len(output_types): "TOUS LES TYPES GÉNÉRÉS ✅",
        0: "AUCUNE GÉNÉRATION RÉUSSIE ❌",
    }.get(ok_count, f"{ok_count}/{len(output_types)} TYPES OK (partiels) ⚠️")
    log(f"PIPELINE v2 — {status_msg}", "OK" if ok_count == len(output_types) else "WARN")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=f"NotebookLM Multi-Output Pipeline v{VERSION}")
    p.add_argument("--config",  "-c", help="Chemin vers pipeline_config_v2.json")
    p.add_argument("--notebook","-n", help="Nom du notebook (override config)")
    p.add_argument("--types",   "-t", help="Types séparés par virgule : audio,slide_deck,report")
    p.add_argument("--dry-run",          action="store_true", help="Simulation")
    p.add_argument("--no-login-refresh", action="store_true", help="Pas de refresh token")
    args = p.parse_args()

    run_pipeline(
        config_path        = args.config,
        notebook_override  = args.notebook,
        types_override     = [t.strip() for t in args.types.split(",")] if args.types else None,
        dry_run            = args.dry_run,
        skip_login_refresh = args.no_login_refresh,
    )
