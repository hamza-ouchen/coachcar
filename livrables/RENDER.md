# Déploiement Render — version cloud 1.2.0

## Où nous en sommes

Le code est prêt pour deux usages : SQLite pour le TP local existant ; PostgreSQL si DATABASE_URL est configurée sur Render. Les anciennes images locales restent utilisables. Les profils et l'historique du PC ne sont pas copiés automatiquement sur Render : le cloud commence avec sa propre base.

Le fichier render.yaml décrit un Web Service Docker Free et une base PostgreSQL Free dans la même région. Aucun disque payant n'est demandé. L'offre Free peut se mettre en veille et la base gratuite expire après 30 jours : vérifier l'échéance dans le compte Render.

## Création dans le tableau de bord, sans terminal

1. Ouvrir dashboard.render.com.
2. Cliquer New + puis Blueprint.
3. Sélectionner hamza-ouchen/coachcar, branche main. Render doit détecter render.yaml.
4. Vérifier que les deux ressources sont bien Free : cap-avenir et cap-avenir-db. Si une offre payante est affichée, ne pas valider et vérifier les champs.
5. Donner un nom au Blueprint, par exemple cap-avenir-tp.
6. Pour CAP_AVENIR_ADMIN_PASSWORD, choisir un mot de passe privé pour la démonstration. L'identifiant sera admin. Le navigateur le demandera à l'ouverture de l'application.
7. Pour OPENROUTER_API_KEY, renseigner la clé du projet dans le champ secret Render. Ne pas l'écrire dans le dépôt ou un fichier public. La clé locale ne se transfère pas automatiquement.
8. Appliquer la configuration et attendre la création de la base puis le premier déploiement. DATABASE_URL est reliée automatiquement par le Blueprint.
9. Ouvrir le Web Service cap-avenir et son adresse https://....onrender.com. Entrer admin et le mot de passe choisi.
10. Vérifier une mission en mode Démonstration, puis l'onglet Exploitation. Il doit afficher Render et PostgreSQL.

L'adresse localhost du PC et les fichiers CMD ne pilotent pas cette application cloud. Le premier déploiement est une installation initiale ; les mises à jour suivantes restent manuelles (autoDeployTrigger off), afin de ne pas contourner l'approbation.

## Vérification après déploiement

- /api/health doit répondre sans mot de passe pour permettre les contrôles Render.
- Le reste de l'application, ses API, dossiers et exports demandent le mot de passe.
- La version doit être 1.2.0.
- Une mission démo doit terminer ; une analyse réelle utilise la clé fournie dans Render et peut être facturée par OpenRouter.
- Dans Exploitation, tester la pause puis la reprise. La pause et l'historique sont dans PostgreSQL et persistent aux redémarrages.
- Les sauvegardes cloud sont des exports applicatifs JSON conservés dans PostgreSQL (trois derniers), pas des sauvegardes physiques pg_dump.

## GitHub et validation humaine

La CI teste SQLite, le workflow, Docker et une vraie base PostgreSQL. La publication GHCR existante conserve son approbation GitHub production. Render ne télécharge pas automatiquement cette image GHCR dans la configuration Blueprint : il construit son image depuis le Dockerfile du commit GitHub sélectionné.

Avant une mise à jour cloud : vérifier la CI de la révision, la faire approuver, suspendre les analyses et exporter l'historique ; dans Render, Manual Deploy permet de choisir la révision à mettre en ligne. Le fait de cliquer Approve dans GitHub ne déploie pas à lui seul sur Render. Une automatisation GitHub → Render peut être configurée séparément avec les identifiants du service et un accès API Render, sans les mettre dans le code.

## Incident et rollback pour le professeur

1. Sur le cloud, ouvrir Exploitation et saisir son nom.
2. Choisir le scénario Lenteur, lancer une mission démo puis activer l'arrêt d'urgence pendant son exécution.
3. Vérifier l'annulation et le refus des nouvelles demandes.
4. Dans Render, montrer l'historique des déploiements et revenir à un déploiement cloud compatible précédent lorsqu'il existe.
5. Vérifier la version et les données, puis réautoriser les analyses et relancer une mission.

Le premier déploiement n'a pas encore de prédécesseur vers lequel revenir. Préparer au moins deux déploiements cloud avant la démonstration du rollback. Ne pas revenir à une version antérieure à l'adaptation PostgreSQL et à la protection par mot de passe.

Un rollback remet le code d'un ancien déploiement ; il ne restaure pas automatiquement PostgreSQL ni les paramètres d'environnement. La pause est conservée volontairement et nécessite une reprise explicite. L'incident choisi dans l'interface est aussi persistant : revenir au scénario Normal pour terminer la répétition.

## Présentation très simple

« GitHub conserve notre code et teste ses modifications. Render construit une image Docker et lance notre application en ligne. PostgreSQL garde les données entre les déploiements. Nous contrôlons les mises à jour, nous simulons les incidents et nous vérifions l'arrêt et la reprise. »

Références : https://render.com/docs/free ; https://render.com/docs/blueprint-spec ; https://render.com/docs/deploys .
