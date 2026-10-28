# Runbook — incident, arrêt et rollback de Cap Avenir

## Préparation

Docker Desktop doit être démarré. Sur la machine préparée, double-cliquer DOCKER.cmd : les images stables et d'incident sont construites si nécessaire, puis l'installation initiale stable est lancée sur http://127.0.0.1:8787 . Une version enregistrée n'est pas reconstruite silencieusement : changer la version pour changer son image.

Le gestionnaire utilise un seul conteneur nommé cap-avenir-demo, les dossiers data/ et runtime/ montés depuis l'hôte, et une seule instance de serveur. Ne pas lancer en parallèle une autre application utilisant la même base. Aucun script ne supprime les données. Le conteneur est exposé uniquement sur l'interface locale. Docker Desktop permet de voir le conteneur et l'image utilisés.

Versions de démonstration : 1.1.1 stable ; 1.1.2-incident.1 préversion dédiée à une panne démo. Cette dernière utilise le même code fonctionnel avec un paramètre d'image qui force l'échec du chercheur Reconversion en mode démonstration. Les analyses réelles ne reçoivent pas cette panne.

## Présentation en classe, 8 à 10 minutes

1. Ouvrir Exploitation, montrer v1.1.1, indiquer son nom pour le journal et réaliser une mission normale en démonstration.
2. Montrer les tests GitHub Actions et les réponses remplacées dans test_workflow.py.
3. Avant approbation, DEPLOYER.cmd avec 1.1.2-incident.1 doit refuser le déploiement. Le service stable ne doit pas changer.
4. Dans Exploitation, lire la candidate, son ID d'image et l'Agent Card. Cocher la confirmation de lecture puis cliquer Approuver. Le nom saisi, l'image, l'horodatage et la revue déclarée de la fiche sont enregistrés. Ne pas confondre cette validation locale avec un contrôle GitHub d'identité.
5. Relancer DEPLOYER.cmd avec la candidate approuvée. Le gestionnaire active la pause, sauvegarde SQLite, remplace le conteneur par l'image exacte approuvée et vérifie /api/health. Le service reste en pause.
6. Vérifier la version affichée, puis cliquer Réautoriser les analyses. Lancer une mission démo : Reconversion échoue et le résultat est partiel ; montrer l'alerte et le correlation_id.
7. Lancer une seconde mission démo. Pendant les premières secondes, ouvrir Exploitation et activer l'arrêt d'urgence. Vérifier que les tâches s'annulent et qu'une nouvelle demande est refusée. Le superviseur ne doit pas démarrer pour la mission annulée.
8. Exécuter ROLLBACK.cmd. Le gestionnaire sauvegarde les données et relance l'image précédente. La version doit redevenir 1.1.1 ; la pause et les missions précédentes restent présentes.
9. Réautoriser les analyses après vérification, lancer une mission normale et constater sa réussite.
10. Exporter le journal JSON et montrer l'Agent Card, les tags Git SemVer et les sauvegardes dans data/backups/.

## Incident sans changement de version

Dans Exploitation, choisir Erreur du fournisseur ou Lenteur, cliquer Appliquer puis Lancer une mission démo. Pour tester tranquillement l'arrêt, le scénario Lenteur garde les chercheurs actifs pendant 30 à 35 secondes. Revenir à Normal après l'exercice. Une image d'incident continue à forcer sa panne démo même si le sélecteur est Normal : le rollback la supprime.

## Procédure d'urgence

1. Activer l'arrêt d'urgence et saisir un motif clair. L'application reste accessible pour l'investigation.
2. Identifier la mission avec son correlation_id, l'étape, les événements et les alertes. Ne pas effacer l'historique.
3. Si une mise à jour est en cause, utiliser ROLLBACK.cmd. Le retour arrière vise une image déjà déployée, pas une image arbitraire.
4. Contrôler la version, la réponse de /api/health, la conservation de la pause et de l'historique.
5. Réautoriser les analyses, puis vérifier une mission démo réussie. Documenter le résultat dans le journal exporté.

Si l'interface est inaccessible : le gestionnaire vérifie l'étiquette de propriété avant d'arrêter un conteneur ; la commande `python scripts/release_manager.py stop` arrête uniquement son conteneur géré et conserve les données. Si l'application ne répond pas avant déploiement, ne pas forcer un remplacement sans diagnostic et sauvegarde. Un retour automatique vers l'image précédente est tenté si la nouvelle image ne devient pas disponible après son lancement.

## Exercice automatique reproductible

Double-cliquer EXERCICE.cmd. Il crée des conteneurs et des volumes de test isolés ; la panne du fournisseur et la décision d'approbation y sont simulées, mais les conteneurs, l'arrêt des tâches, le refus des demandes, les sauvegardes et le rollback sont réels. Aucun appel API et aucune modification de l'historique utilisateur. Rapport local : livrables/exercice-docker.json. La CI produit aussi un rapport d'exercice téléchargeable.

Ce rapport prouve l'exercice technique ; il ne remplace pas l'approbation d'une personne. Vérifier sa date et son champ passed avant de le présenter comme réussi.

## Limites

Les appels déjà reçus par OpenRouter peuvent continuer et être facturés après annulation locale. Le rollback remet le code et la configuration de l'image précédente ; il ne restaure pas automatiquement les données d'une sauvegarde. Les versions du TP conservent une structure SQLite compatible. Les sauvegardes sont conservées pour une restauration manuelle éventuelle. L'installation initiale de la baseline est journalisée comme bootstrap, sans être présentée comme une revue humaine.
