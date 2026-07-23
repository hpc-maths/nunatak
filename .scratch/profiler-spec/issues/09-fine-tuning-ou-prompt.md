# Décision : fine-tuning ou prompt engineering

Type: grilling
Blocked by: 08
Status: resolved

## Question

Le LLM d'explication a-t-il besoin d'un modèle fine-tuné pour le domaine (analyse de kernels HPC), ou le prompt engineering avec un bon contexte déterministe suffit-il ?

Trancher sur la base du prototype (ticket 08) : qualité observée, latence, coût. Si fine-tuning : quelles données d'entraînement (existe-t-il un corpus kernel + diagnostic + optimisation ?), qui l'entretient, et est-ce compatible avec « simple à mettre en place » ? Note (ticket 01) : le fine-tuning dépend du provider choisi au ticket 12, pas de pi.dev.

## Answer

**Prompt engineering, pas de fine-tuning.** Décision prise par l'utilisateur au vu du prototype (ticket 08) : avec un prompt structuré (faits déterministes + source + machine), un bon modèle généraliste orienté code produit des diagnostics exacts et des optimisations d'expert sur les deux kernels de test, y compris le cas « rien à gagner ». Le fine-tuning n'apporterait rien face à ce niveau, coûterait en données et maintenance, et contredirait « simple à mettre en place ». La qualité restant dépendante du modèle choisi dans la config Pi, la spec documentera une recommandation de classe de modèle (orienté code, thinking disponible) plutôt qu'un modèle figé.
