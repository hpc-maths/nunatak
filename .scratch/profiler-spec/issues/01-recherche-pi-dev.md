# Recherche : pi.dev comme provider LLM

Type: research
Status: resolved

## Question

Qu'est-ce que pi.dev exactement et comment s'intègre-t-il dans une librairie Python ?

À établir depuis les sources primaires (site, docs, SDK) :
- Quels modèles sont exposés, et lesquels conviennent à l'analyse de code/kernels ?
- API : REST/SDK Python, authentification, streaming, structured output ?
- Latence et coûts typiques (l'exigence produit : « très performant dans les réponses »).
- Limites : taille de contexte (il faut y faire tenir du code source de kernels + des métriques), rate limits.
- Support éventuel du fine-tuning (alimente le ticket 09).

## Answer

**pi.dev n'est pas un provider d'inférence LLM.** C'est le site officiel de "Pi", un toolkit open source (MIT) d'agents IA d'Earendil Works : harness d'agent de code en TypeScript/Node.js (~75.7k stars, v0.81.1 en juillet 2026).

- Sa couche `@earendil-works/pi-ai` est une API cliente unifiée vers 30+ providers tiers (Anthropic, OpenAI, Google, DeepSeek, Groq, endpoints OpenAI-compatibles comme vLLM/Ollama) en mode "bring your own key". Aucun modèle propre, aucun pricing, aucun service hébergé, aucun fine-tuning.
- Pas de SDK Python : intégration depuis Python uniquement via un subprocess RPC (JSON sur stdin/stdout), donc une dépendance Node.js pour la librairie.
- Homonymes vérifiés : pi.ai (Inflection AI, chatbot grand public, contexte 8K, non orienté code - à écarter) et withpi.ai (Pi Labs, scoring de sorties LLM, pas d'inférence générative - utile au mieux pour évaluer la qualité des explications).
- Latence, coûts, contexte et rate limits sont entièrement hérités du provider tiers choisi ; « très performant » se traduit en choix de modèle, pas en propriété de pi.dev.
- Conséquence : la décision de cadrage « pi.dev ferme » reposait sur une prémisse erronée. Nouvelle décision ouverte dans le ticket 12 (choix du provider LLM). Le fine-tuning (ticket 09) est découplé de pi.dev.

Détails sourcés : `docs/research/pi-dev.md` sur la branche `research/pi-dev` (commit 444f5d4).
