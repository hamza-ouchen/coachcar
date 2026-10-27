# Les trois alertes de Cap Avenir

Toutes les alertes sont enregistrées avec un correlation_id, un agent et un horodatage ; elles apparaissent dans le fil de mission et dans Supervision. Un type d'alerte est enregistré une seule fois par agent et par exécution ; le budget est enregistré une seule fois par workflow.

| Code | Déclencheur réel | Exemple de message | Interprétation |
|---|---|---|---|
| `slow` | Une étape reste active plus de 45 secondes par défaut | Évolution dépasse le seuil de 45 secondes | La recherche ou la génération est lente ; l'étape continue jusqu'à son délai maximal |
| `budget` | La somme des coûts connus dépasse 0,10 USD par défaut | Coût connu : $0.1200, au-dessus du seuil de $0.10 | Dépassement constaté après réception de l'usage ; ce n'est pas un blocage préventif |
| `error` | Une étape échoue : délai, connexion, réponse invalide ou erreur fournisseur | Crédits OpenRouter insuffisants pour cet appel | L'étape est en erreur ; le workflow préserve les dossiers disponibles |

## Démontrer les trois types sans frais

1. Dans Mon orientation, cliquer **Un exemple**.
2. Sélectionner **Démonstration · sans appel API**.
3. Cocher **Simuler les trois types d'alertes**.
4. Cliquer **Explorer mes possibilités**.
5. Les étapes dépassent un seuil pédagogique de 2,5 secondes, déclenchant `slow`.
6. L'agent Reconversion échoue volontairement, déclenchant `error`.
7. Le superviseur travaille avec le dossier Évolution et termine avec un coût simulé de 0,13 USD. La somme simulée dépasse 0,10 USD et déclenche `budget`.
8. Le résultat porte le statut Partielle. Ouvrir Supervision → Démonstrations : les trois types sont visibles.

Le seuil réel reste 45 secondes. Le seuil accéléré de 2,5 secondes est exclusivement utilisé pour ce scénario de démonstration. Les données simulées ne sont jamais mélangées aux métriques réelles.

## Réglages

`SLOW_STEP_SECONDS`, `BUDGET_ALERT_USD` et `STEP_TIMEOUT_SECONDS` dans `.env`. Redémarrer le serveur après modification. Une requête échouée peut avoir un coût fournisseur non retourné : ce coût reste inconnu et n'est pas inventé.
