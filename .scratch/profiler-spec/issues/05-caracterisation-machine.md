# Décision : caractérisation machine (plafonds du roofline)

Type: grilling
Blocked by: 03

## Question

Comment obtenir les plafonds du roofline (peak FLOPs par précision, bandes passantes par niveau mémoire, bande passante réseau) pour la machine de l'utilisateur ?

Options en présence : microbenchmarks embarqués (à la likwid-bench/ERT/STREAM, exécutés une fois puis mis en cache), base de données de specs constructeur embarquée, valeurs théoriques calculées depuis cpuid/nvidia-smi, ou combinaison. Trancher aussi : où est mis en cache le profil machine, et que faire quand le microbenchmark est impossible (nœud partagé, macOS).
