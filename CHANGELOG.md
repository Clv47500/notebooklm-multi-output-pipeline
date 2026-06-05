# Changelog

## [2.0.0] — 2026-06-05
### Added
- 9 types de sortie : audio, vidéo, slides, infographie, rapport, mind map, flashcards, quiz, tableau CSV
- Auth automatique via Comet (Perplexity) — 3 niveaux de fallback
- Artifact configurateur Cowork interactif (pipeline_configurator_v2.html)
- pipeline_runner_v2.py — routeur multi-types, polling, retry
- pipeline_config_v2.json — schéma de configuration complet
- Guide PDF technique 15 pages
- Logs en temps réel dans l'artifact
- Fix : token download expiré → nlm login --force automatique

### Changed
- Auth : Chrome CDP remplacé par Comet (Perplexity) — plus fiable
- Config : passage de pipeline_config.json à pipeline_config_v2.json

### Known Issues
- nlm v0.6.15 : download mind_map retourne null (workaround métadonnées)

## [1.0.0] — 2026-06-01
### Added
- Pipeline initial : infographie uniquement
- pipeline_runner.py — génération depuis notebook NLM
- pipeline_config.json — configuration de base
- Auth via Chrome CDP + cookies Google
