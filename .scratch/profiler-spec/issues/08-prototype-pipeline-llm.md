# Prototype : pipeline LLM (faits d'analyse + source vers conseils)

Type: prototype
Blocked by: 12
Status: resolved

## Question

Avec un vrai kernel (par exemple un stencil ou un GEMM naïf) et des faits d'analyse simulés (position roofline, métriques), quelle qualité de conseils obtient-on du provider LLM choisi au ticket 12, et avec quel prompt/format d'entrée ?

Prototype jetable (script Python) : construire le prompt (faits déterministes + source du kernel + caractéristiques machine), appeler le provider, juger ensemble la pertinence, la latence et le coût des réponses. Le résultat calibre le ticket 09 (fine-tuning ou pas) et fixe le contrat d'interface entre le moteur d'analyse et la couche LLM.

## Answer

Prototype exécuté le 2026-07-23 sur deux kernels (DGEMM naïf memory-bound mal vectorisé ; stencil Jacobi 7 points collé au toit DRAM), avec faits d'analyse simulés réalistes + source + caractéristiques machine, via `pi -p --mode json` et le modèle `opencode-go/kimi-k2.7-code` de la config Pi de l'utilisateur.

**Verdict qualité (jugement utilisateur) : suffisant sans fine-tuning.** Diagnostics exacts et fidèles aux faits mesurés sur les deux cas, y compris le cas piège (le stencil à 92 % de bande passante : le modèle reconnaît le plafond, propose cache blocking, blocage temporel avec ses contraintes d'interface, OpenMP avec le caveat bande passante partagée). Optimisations ordonnées avec extraits de code corrects et gains plausibles.

**Mesures** : latence 35-60 s/kernel avec thinking, 24 s sans ; coût ~0,01-0,014 $/kernel (négligeable). **Décision utilisateur pour la spec : appels parallèles sur les top-N kernels + streaming des explications dans le terminal** (~1 min pour 5 kernels), le rapport HTML se remplissant à la fin.

**Contrat d'interface validé** : prompt = système (rôle moteur d'explication, interdiction de contredire les faits, format markdown ~400 mots) + JSON machine + JSON faits mesurés + source. Parsing : événements JSON de pi, texte dans les blocs `content` du `message_end` assistant.

**Exigence découverte en passant** : le provider par défaut de la config Pi était en dépassement de budget (429) - le pipeline DOIT détecter `stopReason: error`/`errorMessage` et soit basculer sur un autre modèle configuré, soit expliquer clairement l'absence d'explications dans le rapport.

Prototype capturé sur la branche `prototype/llm-pipeline` (`prototype/llm_pipeline_prototype.py`).
