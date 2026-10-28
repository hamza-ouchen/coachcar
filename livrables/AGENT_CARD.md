# Agent Card — Cap Avenir

Version fonctionnelle : 1.1.0. Projet pédagogique local. Responsable : propriétaire du dépôt hamza-ouchen/coachcar. Dernière mise à jour : 28 octobre 2026.

## Identité, rôles et interfaces

| Agent | Entrées | Mission | Sortie | Outils |
|---|---|---|---|---|
| Évolution | Profil, compétences, marché, objectifs et contraintes | Identifier une spécialisation accessible dans le domaine actuel | Dossier JSON : résumé, compétences, opportunités, signaux, limites, sources | Modèle OpenAI via OpenRouter, recherche Exa via openrouter:web_search |
| Reconversion | Même profil | Explorer deux domaines voisins, retenir une piste et identifier les compétences transférables | Même structure de dossier JSON | Même modèle et outil de recherche |
| Superviseur | Profil et deux dossiers, ou dossier disponible et erreur de l'autre branche | Comparer les trajectoires, expliquer la recommandation et proposer les étapes 30/60/90 jours | Recommandation JSON, comparaison, raisons, première action, incertitudes | Modèle OpenAI via OpenRouter, sans recherche supplémentaire |

Modèle par défaut : openai/gpt-4.1-mini ; configurable. Instructions dans provider.py. LangGraph exécute les deux recherches en parallèle puis une jointure vers le superviseur. Mémoire : état partagé par mission ; historique SQLite local. Pas d'entraînement de modèle ni de mémoire personnelle externe.

## Limites et critères de qualité

Les recommandations sont indicatives et ne remplacent pas un conseiller professionnel. Des offres trouvées ne constituent ni une mesure exhaustive de demande ni une garantie d'emploi. Les projections sur l'avenir d'un métier restent incertaines. Les citations retournées par l'outil attestent de métadonnées de source, pas de la vérité automatique des conclusions. Les tests déterministes ne certifient pas la pertinence sémantique de toutes les réponses réelles.

Contraintes : deux recherches maximum par agent de recherche selon l'outil configuré, huit résultats maximum par appel, sortie limitée à 2600 tokens, délai d'appel de 90 secondes, aucun retry payant automatique. Les frais déjà engagés peuvent subsister après l'arrêt local.

## Autorisations et données

Les agents peuvent lire les données du profil et rechercher sur le web. Ils ne peuvent ni réserver, ni candidater, ni envoyer de messages, ni modifier des comptes. Le serveur conserve profils, dossiers, événements et métriques dans SQLite. La clé est fournie à l'exécution, jamais intégrée à l'image Docker ou aux exports. Une analyse réelle transmet le profil au fournisseur et éventuellement aux services de recherche concernés.

## Contrôles d'exploitation

- Pause persistante en base : refuse les nouvelles analyses et annule les tâches locales actives.
- Vérification de pause à l'entrée de chaque nœud, événements d'annulation et conservation des dossiers terminés.
- Incidents de fournisseur simulés uniquement en mode démonstration.
- Approbation nominative locale portant sur l'ID exact d'une image candidate ; les scripts refusent son déploiement avant approbation.
- Installation initiale stable distinguée de l'approbation d'une mise à jour. Rollback d'urgence autorisé vers une image déjà déployée.
- Sauvegarde SQLite avant remplacement, pause conservée au rollback et reprise explicite après contrôle.
- Le serveur applicatif n'a pas accès au socket Docker : les scripts de l'hôte exécutent les remplacements.

## Portée de la validation

La validation technique est vérifiée par les tests Python, les contrôles navigateur et l'exercice Docker décrit dans RUNBOOK.md. L'exercice automatisé nomme son approbateur « Test automatique (approbation simulée) » et ne constitue pas une approbation humaine.

La validation humaine d'une candidate est enregistrée lors du clic Approuver, avec nom, date et image exacte, dans le registre local et le journal. Le nom saisi est déclaratif : cet espace est destiné au TP local sur loopback, sans mécanisme d'authentification d'identité. Une mise en production partagée nécessiterait une authentification et des autorisations adaptées.

Statut de revue humaine de cette fiche : à confirmer par l'étudiant ou le professeur après lecture. Ne pas présenter une revue automatique comme une signature humaine. Exporter le journal JSON après l'approbation pour joindre sa preuve.
