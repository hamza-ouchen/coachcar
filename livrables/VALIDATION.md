# Vérifications de livraison

Validation réalisée le 26 octobre 2026 sur Windows, Python 3.12.4 et Chrome.

## API réelle

Une analyse complète a été exécutée avec `openai/gpt-4.1-mini` via OpenRouter :

- Trois étapes terminées : Évolution, Reconversion, Superviseur.
- Deux recherches web confirmées par les métadonnées de citations.
- Durée totale : 28,662 secondes.
- Tokens cumulés : 13 173.
- Coût retourné : 0,0369928 USD.
- Seize citations au total dans les deux dossiers, sans déduplication entre agents.
- Recommandation et trois étapes de feuille de route reçues.
- Correlation ID : `723d9257-c1b3-4b31-b21e-ffa782970f6c`.

Ces valeurs décrivent cet essai, pas une garantie de durée ou de coût pour les prochaines analyses. Un appel de vérification préalable de recherche a également été réalisé et facturé séparément.

## Tests d'intégration : 6 réussis

1. Recherches parallèles, jointure du superviseur, corrélation et somme d'usage.
2. Résultat partiel et coût inconnu correctement représentés.
3. Deux recherches échouées : superviseur non appelé.
4. Trois types d'alertes et absence de doublon d'alerte budget.
5. Validation des entrées, routes, exports et absence de clé dans la réponse health.
6. Historique conservé, exécution active marquée interrompue après redémarrage.

## Navigateur : 10 vérifications réussies

Formulaire ; workflow parallèle ; actualisation pendant l'analyse avec reprise SSE ; rapport ; détail d'agent ; replay sans création d'exécution ; restauration après actualisation ; dashboard de supervision ; trois types d'alertes simulés ; mobile à 390 px sans débordement horizontal.

Aucune erreur JavaScript détectée pendant ces parcours. Captures enregistrées dans artifacts/ sur la machine de développement. Dépendances vérifiées avec pip check : aucun conflit détecté.

## Limites explicites

- Exécution locale : pas de déploiement public.
- Effet de perspective CSS/SVG, pas de moteur de rendu WebGL.
- Les phases internes d'un appel fournisseur ne sont pas instrumentées séparément.
- Les coûts non retournés par le fournisseur restent inconnus.
- La disponibilité des recherches et modèles dépend d'OpenRouter ; le mode démonstration ne dépend pas de l'API.
