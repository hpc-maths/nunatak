# Prototype : pipeline LLM (faits d'analyse + source vers conseils)

Type: prototype
Blocked by: 01

## Question

Avec un vrai kernel (par exemple un stencil ou un GEMM naïf) et des faits d'analyse simulés (position roofline, métriques), quelle qualité de conseils obtient-on de pi.dev, et avec quel prompt/format d'entrée ?

Prototype jetable (script Python) : construire le prompt (faits déterministes + source du kernel + caractéristiques machine), appeler pi.dev, juger ensemble la pertinence, la latence et le coût des réponses. Le résultat calibre le ticket 09 (fine-tuning ou pas) et fixe le contrat d'interface entre le moteur d'analyse et la couche LLM.
