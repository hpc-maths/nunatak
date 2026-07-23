# Décision : choix du provider LLM et de la couche d'accès

Type: grilling

## Question

La recherche pi.dev (ticket 01) a montré que pi.dev n'est pas un provider d'inférence : c'est le toolkit d'agents "Pi" (TypeScript/Node.js), dont la couche pi-ai est un client unifié bring-your-own-key vers 30+ providers. Il faut donc re-décider :

1. Quel(s) provider(s) d'inférence viser (Anthropic, OpenAI, Google, endpoint local vLLM/Ollama pour les clusters sans accès internet...) ?
2. Quelle couche d'accès dans notre librairie Python : interface provider-agnostique maison, SDK d'un provider unique, ou adopter Pi via subprocess Node.js (ce qui ajoute une dépendance lourde et contredit « simple à mettre en place ») ?

À garder en tête : les nœuds de calcul HPC n'ont souvent pas d'accès internet sortant - le support d'un endpoint OpenAI-compatible auto-hébergé est probablement incontournable.
