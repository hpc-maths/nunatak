# Décision : attribution kernel vers code source

Type: grilling
Blocked by: 04

## Question

Comment remonter d'un kernel/hotspot mesuré au code source à montrer au LLM et à l'utilisateur, pour chaque famille de langages de la v1 ?

À trancher : exploitation DWARF pour les compilés (que faire des binaires sans -g ? inlining ?), chemin Python (py-spy / perf-trampoline), kernels GPU (mapping nom de kernel CUDA/HIP vers source, PTX/SASS utile au LLM ?), et la politique quand le source est introuvable (analyse au niveau assembleur ? dégradation ?).
