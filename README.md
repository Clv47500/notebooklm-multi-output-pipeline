# 🎙️ NotebookLM Multi-Output Pipeline v2.0

Pipeline automatisé pour générer **9 types de sortie** depuis n'importe quel notebook NotebookLM — audio, vidéo, slides, infographie, rapport, mind map, flashcards, quiz, tableau CSV — avec authentification automatique via **Comet (Perplexity)** et interface de configuration **Cowork**.

## ✨ Fonctionnalités

- **9 formats** : audio (.m4a), vidéo (.mp4), slides (.pdf/.pptx), infographie (.png), rapport (.md), mind map (.json), flashcards (.html), quiz (.html), tableau (.csv)
- **Auth automatique** via Comet (Perplexity) — zéro intervention manuelle
- **Configurateur Cowork** — interface graphique intégrée à Claude Desktop
- **Logs temps réel** dans l'artifact pendant l'exécution
- **Gestion d'erreurs** avec continue_on_error et retry automatique
- **Backup v1** dans `v1_backup/`

## 🚀 Installation

```bash
pip install notebooklm-tools
```

**Prérequis** : Python 3.10+ · Comet (Perplexity) · nlm CLI v0.6.15+

## 📖 Usage

```bash
# Notebook + types spécifiques
python pipeline_runner_v2.py --notebook "Mon Notebook" --types audio,slide_deck,report

# Config JSON
python pipeline_runner_v2.py --config config/pipeline_config_v2.json

# Dry-run
python pipeline_runner_v2.py --dry-run
```

## 📁 Structure

```
├── pipeline_runner_v2.py          # Script principal v2
├── setup_chrome_cdp.py            # Setup raccourcis Chrome (optionnel)
├── config/pipeline_config_v2.json # Config complète (template)
├── artifacts/pipeline_configurator_v2.html  # Widget Cowork
├── docs/guide_notebooklm_pipeline_v2.pdf    # Guide 15 pages
└── v1_backup/                     # Pipeline v1 (infographie uniquement)
```

## ⚠️ Bugs connus nlm v0.6.15

| Type | Problème | Fix intégré |
|---|---|---|
| audio/video | Download 302 si token expiré | nlm login --force automatique |
| mind_map | Response Data null | Métadonnées + lien NLM |

## 📄 Licence

MIT — Christian Levannier · 2026
