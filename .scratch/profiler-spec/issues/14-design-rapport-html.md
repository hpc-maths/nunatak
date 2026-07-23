# Décision : design du rapport HTML

Type: prototype

## Question

À quoi ressemble le rapport HTML auto-contenu, et quelles vues/interactions offre-t-il, maintenant que le modèle de données (ticket 06) est fixé ?

Le rapport est une mini-app TypeScript embarquée, alimentée par le pivot mesuré (Hotspot/Locus/Mesure/Événement) plus le Diagnostic recalculé et l'Explication LLM. À trancher via /prototype (variations d'UI sur des données d'exemple) : la vue roofline interactive (plafonds, points par Hotspot, qualité mesuré/estimé visible), la timeline (flux d'Événements, MPI par rang), la vue par Hotspot (métriques + source + Explication étiquetée « conseil »), la synthèse des bottlenecks, et comment le déséquilibre de charge entre Loci est rendu. Contrainte : auto-contenu, fonctionne sur cluster sans serveur, sans requête externe.
