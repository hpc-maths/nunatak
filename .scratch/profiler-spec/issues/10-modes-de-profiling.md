# Décision : modes de profiling et budget d'overhead

Type: grilling
Blocked by: 03, 04
Status: resolved

## Question

Un run suffit-il, ou le roofline exige-t-il plusieurs exécutions (multiplexing de compteurs, groupes de compteurs incompatibles), et quel budget d'overhead s'impose-t-on ?

Trancher : sampling vs counting par plateforme, stratégie de multiplexing, nombre de runs acceptable pour l'UX zéro-instrumentation (« nunatak run » peut-il relancer l'application ?), overhead maximal toléré (en % du temps d'exécution), et ce qu'on dégrade quand le budget est dépassé.

## Answer

Décision prise en session /grilling ; arbitrage complet dans `docs/adr/0003-modes-de-profiling.md`.

Cadre imposé par les tickets 03 et 04 : le comptage par région de LIKWID exige des marqueurs dans le source, donc hors jeu. Sans instrumentation, attribuer des compteurs à un Hotspot n'a qu'une voie, **l'échantillonnage déclenché par événement**.

**Une exécution par défaut**, groupes d'événements multiplexés par le noyau ; mode multi-passes explicite pour des compteurs exacts, jamais imposé - relancer d'autorité une application dans une allocation payée n'est pas à l'outil de le décider. Un compteur multiplexé reste « mesuré » tant que sa couverture `time_running / time_enabled` dépasse le seuil (~80 %), « estimé » en dessous.

**GPU en une seule exécution** : `nsys` sur toute la timeline, `ncu` borné à quelques lancements par nom de kernel (warm-up exclu), donc rejeu limité à une poignée de lancements. Roofline GPU disponible par défaut, sur un échantillon dont la couverture est annoncée.

**Budget de 10 % de temps mural tenu par construction** (le mesurer exigerait une exécution de référence), fréquence d'échantillonnage adaptative à la durée et au débit observés. **Plancher statistique par Hotspot** : erreur relative conservée, rétrogradation en « estimé » sous le plancher, agrégat « autres » plus bas, et le LLM ne reçoit jamais un Hotspot sous le plancher.

**Multi-passes protégé par un groupe témoin** (cycles + instructions dans chaque passe) : écart inter-passes au-delà du seuil = application non reproductible, Mesures fusionnées rétrogradées en « estimé ». Une invocation reste un seul Run, chaque Mesure traçant sa Passe.

**Deux niveaux de collecte à l'échelle** : comptage sur tous les rangs (déséquilibre, totaux, volumes MPI, coût constant), échantillonnage sur un rang par nœud plus le rang 0 au-delà d'environ 64 rangs. Hotspots des Loci non échantillonnés : « indisponible », jamais extrapolés.

**macOS** : pas d'échantillonnage par événement (kperf écarté au ticket 02), donc échantillonnage temporel - `xctrace` si Xcode, `/usr/bin/sample` sinon - plus `powermetrics` pour les agrégats. Compteurs par Hotspot « indisponible ».

**Ordre de sacrifice fixe** quand tout ne rentre pas : temps par Hotspot et agrégats par rang, puis trafic mémoire, puis FLOPs par précision, puis caches, détail GPU et assembleur.
