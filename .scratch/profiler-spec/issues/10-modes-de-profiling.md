# Décision : modes de profiling et budget d'overhead

Type: grilling
Blocked by: 03, 04

## Question

Un run suffit-il, ou le roofline exige-t-il plusieurs exécutions (multiplexing de compteurs, groupes de compteurs incompatibles), et quel budget d'overhead s'impose-t-on ?

Trancher : sampling vs counting par plateforme, stratégie de multiplexing, nombre de runs acceptable pour l'UX zéro-instrumentation (« profiler run » peut-il relancer l'application ?), overhead maximal toléré (en % du temps d'exécution), et ce qu'on dégrade quand le budget est dépassé.
