# Décision : packaging et distribution

Type: grilling

## Question

Comment la librairie est-elle installée et distribuée pour rester « simple à mettre en place » sur cluster HPC, poste Linux et Mac ?

Le ticket 04 a établi que tous les collecteurs sont orchestrés en sous-processus (aucun linkage) : un paquet Python pur avec assets TS précompilés est donc plausible. Trancher : pip/PyPI seul ou aussi conda-forge et spack ; politique vis-à-vis des collecteurs absents (installation guidée ? bundling interdit pour nsys/ncu - EULA) ; versions Python supportées ; comment la commande `doctor` (ticket 04) s'articule avec l'installation.

Note issue du ticket 12 : Node.js + pi (pi.dev) sont des prérequis REQUIS - le packaging doit couvrir leur détection/installation guidée, y compris sur cluster sans droits admin.
