# Décision : choix du provider LLM et de la couche d'accès

Type: grilling
Status: resolved

## Question

La recherche pi.dev (ticket 01) a montré que pi.dev n'est pas un provider d'inférence : c'est le toolkit d'agents "Pi" (TypeScript/Node.js), dont la couche pi-ai est un client unifié bring-your-own-key vers 30+ providers. Il faut donc re-décider :

1. Quel(s) provider(s) d'inférence viser (Anthropic, OpenAI, Google, endpoint local vLLM/Ollama pour les clusters sans accès internet...) ?
2. Quelle couche d'accès dans notre librairie Python : interface provider-agnostique maison, SDK d'un provider unique, ou adopter Pi via subprocess Node.js (ce qui ajoute une dépendance lourde et contredit « simple à mettre en place ») ?

À garder en tête : les nœuds de calcul HPC n'ont souvent pas d'accès internet sortant - le support d'un endpoint OpenAI-compatible auto-hébergé est probablement incontournable.

## Answer

**La configuration de Pi est la source unique d'accès aux modèles.** Décisions :

1. **Couche d'accès** : le profiler pilote Pi en subprocess RPC (`pi --mode rpc --no-session`, JSON sur stdin/stdout). Aucun SDK provider n'est intégré côté Python. Le principe « exec + parse » des collecteurs (ticket 04) s'étend au LLM : `pi` est un outil externe orchestré, comme perf ou nsys.
2. **Providers et modèles** : entièrement délégués à la config de Pi (clés par variables d'environnement, OAuth des abonnements Claude/ChatGPT, endpoints OpenAI-compatibles vLLM/Ollama pour les clusters sans accès internet). Le profiler utilise le modèle par défaut de Pi, surchargeable par un flag CLI (`--model`).
3. **Statut de la dépendance : requise.** Node.js + pi sont des prérequis d'installation du profiler (décision utilisateur, contre la recommandation « optionnelle »). La commande `doctor` vérifie leur présence et la validité de la config Pi. Conséquence propagée au ticket 13 (packaging).

Le prototype (ticket 08) validera la qualité et la latence des réponses à travers ce chemin RPC ; il est maintenant débloqué.

Assoupli par le ticket 13 : Node.js et pi ne sont plus des prérequis **durs**. Ils sont alignés sur le motif de dégradation fonctionnelle nommée qui régit tout le reste (piles d'appels, LLVM, source, collecteurs) - déclarés en dépendances sur conda-forge et spack donc présents par défaut, mais leur absence produit « Explication indisponible » plutôt qu'un refus d'installation. L'architecture le commande : le Diagnostic déterministe ne dépend en rien du LLM, et un prérequis dur refuserait l'outil à un utilisateur sur cluster coupé du réseau, à qui tout le cœur serait utile.
