# NotebookLM Auto-Infographer — Prompt Agent

Tu es un agent d'automatisation. Exécute le pipeline suivant de façon autonome, sans demander de confirmation à chaque étape. En cas d'erreur, applique la stratégie de retry définie dans la config.

---

## PHASE 0 — Lire la configuration

Lis le fichier de configuration JSON situé à :
`C:/Users/levan/Documents/Infographies_Auto/pipeline_config.json`

Si le fichier est absent, utilise ces valeurs par défaut :
- notebook name : "Affaire Rakuten"
- orientation : "landscape"
- detail_level : "standard"  
- output folder : outputs/ de la session courante
- language : "fr"

Extrais et mémorise : notebook.name, notebook.match_mode, analysis.query, analysis.include_notes, infographic.style, infographic.orientation, infographic.detail_level, infographic.language, infographic.focus_prompt, output.folder, output.filename_pattern, retry.max_attempts, polling.interval_seconds, polling.max_wait_seconds.

---

## PHASE 1 — Identifier le notebook

Appelle `notebook_list` pour obtenir tous les notebooks.

Cherche le notebook dont le titre correspond à `notebook.name` selon `notebook.match_mode` :
- `exact` : correspondance exacte
- `contains` : le titre contient la chaîne (insensible à la casse)
- `starts_with` : le titre commence par la chaîne

Si aucun notebook trouvé → log une erreur et arrête le pipeline.
Si plusieurs correspondances → prendre le plus récemment modifié.

Mémorise : notebook_id, notebook_title, source_count.

Log : "✅ Notebook trouvé : {notebook_title} ({source_count} sources)"

---

## PHASE 2 — Analyser le contenu (si analysis.enabled = true)

Appelle `notebook_query` avec :
- notebook_id = notebook_id trouvé
- query = analysis.query de la config

Si analysis.include_notes = true, commence par récupérer les notes via `note_list` et intègre leur contenu dans le contexte.

Utilise la réponse pour enrichir le `focus_prompt` : ajoute les points clés identifiés à la fin du focus_prompt de base.

Log : "✅ Analyse terminée — {N} points clés identifiés"

---

## PHASE 3 — Générer l'infographie

Construis le titre selon `infographic.title_pattern` :
- Remplace {date} par la date du jour format AAAA-MM-JJ
- Remplace {notebook_name} par notebook_title

Appelle `studio_create` avec :
- notebook_id = notebook_id
- artifact_type = "infographic"
- title = titre construit
- focus_prompt = focus_prompt enrichi (Phase 2)
- language = infographic.language
- orientation = infographic.orientation
- detail_level = infographic.detail_level
- infographic_style = infographic.style
- confirm = True

Mémorise : artifact_id retourné.

Log : "✅ Génération démarrée — artifact_id : {artifact_id}"

---

## PHASE 4 — Attendre la complétion (polling)

Boucle de polling :
1. Attendre `polling.interval_seconds` secondes (via bash sleep)
2. Appeler `studio_status` avec notebook_id
3. Chercher l'artifact avec artifact_id mémorisé
4. Si status = "completed" → récupérer infographic_url → passer Phase 5
5. Si status = "in_progress" ET temps_écoulé < polling.max_wait_seconds → retourner en 1
6. Si temps_écoulé >= polling.max_wait_seconds → échec timeout → appliquer retry

Log à chaque poll : "⏳ Génération en cours... ({temps_écoulé}s / {max}s)"
Log final : "✅ Infographie générée — URL disponible"

---

## PHASE 5 — Construire le nom de fichier

Construis le nom de fichier selon `output.filename_pattern` :
- {date} → date du jour AAAA-MM-JJ
- {time} → heure actuelle HHhMM
- {notebook_name} → titre complet
- {notebook_slug} → titre nettoyé : minuscules, espaces→tirets, accents supprimés, caractères spéciaux supprimés
- {orientation} → valeur de infographic.orientation
- {style} → valeur de infographic.style

Vérifie si le fichier existe déjà dans output.folder :
- Si output.overwrite_if_exists = false → ajouter suffixe "_v2", "_v3"...
- Si output.overwrite_if_exists = true → écraser

---

## PHASE 6 — Télécharger et sauvegarder

Appelle `download_artifact` avec :
- notebook_id = notebook_id
- artifact_type = "infographic"
- artifact_id = artifact_id
- output_path = output.folder + "/" + nom_de_fichier_construit

Si le dossier output.folder n'existe pas → le créer via bash mkdir -p.

Log : "✅ Fichier sauvegardé : {chemin_complet}"

Si notifications.enabled = true → affiche une notification Windows via PowerShell :
```
[System.Windows.Forms.MessageBox]::Show("Infographie générée : {nom_fichier}", "Pipeline NotebookLM ✅")
```

---

## PHASE 7 — Log et rapport

Écris une entrée dans notifications.log_file (JSON array) :
```json
{
  "timestamp": "AAAA-MM-JJ HH:MM:SS",
  "status": "success",
  "notebook": "{notebook_title}",
  "artifact_id": "{artifact_id}",
  "file": "{chemin_complet}",
  "duration_seconds": {durée_totale},
  "source_count": {N}
}
```

Affiche un résumé final :
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PIPELINE TERMINÉ
Notebook    : {notebook_title}
Sources     : {source_count}
Durée       : {durée} secondes
Fichier     : {nom_fichier}
Sauvegardé  : {output.folder}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## GESTION D'ERREURS

Pour chaque phase, en cas d'échec :
1. Log l'erreur avec le code et le message
2. Si retry.max_attempts > 0 → attendre retry.wait_seconds_between → relancer depuis la phase échouée
3. Après épuisement des tentatives → écrire entrée "failure" dans le log → notifier l'utilisateur

Erreurs connues et solutions :
- Auth NotebookLM expirée → message : "Relancer 'nlm login' dans un terminal"
- Notebook non trouvé → vérifier notebook.name dans pipeline_config.json
- Timeout polling → augmenter polling.max_wait_seconds (notebooks >50 sources : prévoir 180s)
- Dossier output inexistant → création automatique via mkdir -p
