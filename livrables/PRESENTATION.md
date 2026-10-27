# Démonstration de classe — 5 à 7 minutes

## 1. Présenter le besoin (30 s)

« Cap Avenir aide à comparer deux trajectoires professionnelles : progresser dans son domaine ou explorer une reconversion. Deux agents recherchent et un superviseur compare leurs dossiers. Le TP porte aussi sur l'observabilité de leur travail. »

## 2. Faire une analyse réelle (1 à 2 min)

Ouvrir LANCER.cmd, cliquer Un exemple, garder Analyse réelle, puis Explorer mes possibilités. Les appels sont facturés sur le compte OpenRouter configuré.

Montrer que les deux recherches commencent en parallèle et que le superviseur attend les deux dossiers. Cliquer une station : dossier, sources et événements. La durée réelle varie selon le fournisseur et les recherches.

## 3. Montrer le résultat (1 min)

Présenter la recommandation, les deux trajectoires, les technologies, les sources et le plan 30/60/90 jours. Souligner les incertitudes : les agents donnent des pistes, sans garantir l'avenir d'un métier ni un emploi.

## 4. Montrer l'instrumentation (1 min)

Ouvrir Supervision → Analyses réelles. Montrer le correlation_id, la durée, les tokens, le coût connu et le détail du journal. Montrer la comparaison par agent et la projection sur 100 orientations.

Exporter Workflow JSON et Exécutions CSV : ce sont les livrables demandés.

## 5. Montrer le replay et les alertes (1 à 2 min)

Ouvrir une mission terminée et cliquer Rejouer (×4 pour accélérer). Aucun appel API n'est réalisé.

Revenir au formulaire, choisir Démonstration et cocher Simuler les trois types d'alertes. Lancer puis ouvrir Supervision → Démonstrations : lenteur, erreur et budget sont visibles. Expliquer le statut Partielle et la conservation du dossier disponible.

## Si le réseau est indisponible

La démonstration locale fonctionne sans appel API. Un exemple réel et ses événements sont déjà présents dans l'historique et dans exemple-analyse-reelle.json. Ne pas présenter les données de démonstration comme de vraies recherches.

## Expliquer le code en une phrase

« FastAPI sert l'interface, LangGraph exécute deux branches parallèles puis une jointure vers le superviseur, OpenRouter fournit le modèle OpenAI et la recherche web, SQLite conserve les événements, et SSE met le dashboard à jour. »
