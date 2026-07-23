# Décision : fine-tuning ou prompt engineering

Type: grilling
Blocked by: 08

## Question

Le LLM d'explication a-t-il besoin d'un modèle fine-tuné pour le domaine (analyse de kernels HPC), ou le prompt engineering avec un bon contexte déterministe suffit-il ?

Trancher sur la base du prototype (ticket 08) : qualité observée, latence, coût. Si fine-tuning : quelles données d'entraînement (existe-t-il un corpus kernel + diagnostic + optimisation ?), qui l'entretient, et est-ce compatible avec « simple à mettre en place » ? Note (ticket 01) : le fine-tuning dépend du provider choisi au ticket 12, pas de pi.dev.
