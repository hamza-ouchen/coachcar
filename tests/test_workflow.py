"""Integration checks on an isolated SQLite database; no paid API calls."""
# Ce fichier contient 6 tests du fonctionnement de l'application.
# Chaque test suit la même idée : préparer une situation, l'exécuter,
# puis vérifier que le résultat correspond à ce qu'on attend.

# asyncio : exécuter le workflow asynchrone et simuler de petites attentes.
import asyncio
# tempfile : créer un dossier provisoire pour la base de données de test.
import tempfile
# unittest : outil Python qui lance les tests et signale leurs résultats.
import unittest
# Path : construire des chemins de fichiers, sur Windows comme sur Linux.
from pathlib import Path
# patch : remplacer temporairement une fonction ou une valeur pendant un test.
from unittest.mock import patch
# uuid4 : générer un identifiant unique pour chaque analyse de test.
from uuid import uuid4

# TestClient : appeler notre API directement en Python, sans navigateur
# et sans lancer un serveur qui écoute sur un port réseau.
from fastapi.testclient import TestClient

# Les vrais modules de notre application que les tests vont utiliser.
import app
import provider
import storage
import workflow

# Profil fictif commun aux tests : pas besoin de remplir le formulaire à la main.
PROFILE = {"situation": "Développeur junior", "skills": "Python, SQL", "objective": "compare", "market": "Maroc", "remote": True, "hours": 8, "horizon": 6, "interests": "Data"}


# Cette classe regroupe les tests. Hériter de unittest.TestCase nous donne
# les vérifications assertEqual, assertTrue, etc. « self » désigne le test courant.
class WorkflowChecks(unittest.TestCase):
    # unittest appelle automatiquement setUp AVANT CHAQUE test.
    # Chaque test commence donc avec sa propre base vide, indépendante des autres.
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # Garder le chemin habituel pour pouvoir le remettre après le test.
        self.previous_db = storage.DB_PATH
        # Rediriger le stockage vers test.db dans le dossier temporaire.
        # On ne travaille pas sur data/cap_avenir.db et son historique réel.
        storage.DB_PATH = Path(self.temp.name) / "test.db"
        # Créer les tables dans cette base temporaire.
        storage.init_db()

    # unittest appelle automatiquement tearDown APRÈS CHAQUE test.
    def tearDown(self):
        # Rétablir le chemin habituel et supprimer le dossier de test.
        storage.DB_PATH = self.previous_db
        self.temp.cleanup()

    # Fonction d'aide commune : elle n'est pas un test à elle seule,
    # car son nom ne commence pas par test_.
    # « function » est la fausse réponse d'agent définie par le test qui l'appelle.
    def run_workflow(self, function):
        run_id = str(uuid4())
        storage.create_run(run_id, PROFILE, "demo", "test-model")
        # Pendant ce bloc « with », demo_agent est remplacée par notre fonction.
        # Le vrai graphe LangGraph s'exécute, avec des réponses contrôlées.
        # Aucun modèle ni moteur de recherche payant n'est appelé.
        with patch.object(provider, "demo_agent", function):
            # asyncio.run démarre le traitement asynchrone et attend sa fin.
            asyncio.run(workflow.execute(run_id, PROFILE, demo=True))
        # À la sortie du bloc, patch remet automatiquement la fonction d'origine.
        # Renvoyer la mission enregistrée ET son journal d'événements.
        return storage.get_run(run_id), storage.events(run_id)

    # TEST 1 : les deux recherches réussissent, puis le superviseur répond.
    def test_parallel_research_join_and_billing(self):
        # Un « stub » est ici une fonction qui fournit une réponse simulée.
        # async/await permettent de patienter sans bloquer les autres agents.
        async def stub(agent, profile, dossiers=None, scenario="normal"):
            # Attentes simulées : Évolution 0,04 s, Reconversion 0,08 s,
            # Superviseur 0,01 s. Ce sont des secondes, pas des coûts.
            await asyncio.sleep(.04 if agent == "evolution" else .08 if agent == "reconversion" else .01)
            if agent == "supervisor":
                # Le superviseur doit avoir reçu les deux dossiers avec un résumé.
                self.assertIn("summary", dossiers["evolution"])
                self.assertIn("summary", dossiers["reconversion"])
                # On renvoie deux éléments : le dossier et les métriques d'usage.
                return {"recommendation": "Test", "recommended_path": "Python"}, {"prompt_tokens": 20, "completion_tokens": 10, "cost": .02}
            # Chacun des deux chercheurs renvoie 15 tokens et un coût de 0,01 $.
            return {"summary": agent, "sources": []}, {"prompt_tokens": 10, "completion_tokens": 5, "cost": .01}

        # Exécuter le scénario, puis contrôler le résultat stocké.
        run, events = self.run_workflow(stub)
        self.assertEqual(run["status"], "completed")
        # Coût attendu : 0,01 + 0,01 + 0,02 = 0,04 $.
        # AlmostEqual compare des nombres décimaux avec une petite tolérance
        # pour les arrondis de représentation des nombres en Python.
        self.assertAlmostEqual(run["cost"], .04)
        # Tokens attendus : 15 + 15 + 30 = 60.
        self.assertEqual(run["tokens"], 60)
        # Parcourir les événements pour créer deux dictionnaires :
        # starts associe chaque agent à son instant de démarrage ; ends à sa fin.
        # Exemple : starts = {"evolution": 2.1, "reconversion": 3.4, ...}, en ms.
        starts = {e["agent"]: e["elapsed_ms"] for e in events if e["type"] == "agent_started"}
        ends = {e["agent"]: e["elapsed_ms"] for e in events if e["type"] == "agent_completed"}
        # Reconversion doit commencer AVANT la fin d'Évolution : leurs travaux
        # se chevauchent, ce qui vérifie le parallélisme sur ce scénario.
        self.assertLess(starts["reconversion"], ends["evolution"])
        # Le superviseur doit commencer APRÈS la fin des deux recherches.
        # max(...) donne la plus tardive des deux fins.
        self.assertGreaterEqual(starts["supervisor"], max(ends["evolution"], ends["reconversion"]))
        # all(...) signifie « tous » : tous les événements concernent cette mission.
        self.assertTrue(all(e["run_id"] == run["id"] for e in events))
        # Deux handoffs = deux transmissions de dossier vers le superviseur.
        self.assertEqual(len([e for e in events if e["type"] == "handoff"]), 2)
        # La démo ne doit pas augmenter les statistiques des analyses réelles.
        self.assertEqual(storage.metrics("live")["total"], 0)
        # Une mission démo réussie, au coût complet, peut servir à sa projection démo.
        self.assertEqual(storage.metrics("demo")["projection_sample"], 1)

    # TEST 2 : une recherche échoue et l'autre n'indique pas son coût.
    def test_partial_and_unknown_cost(self):
        async def stub(agent, profile, dossiers=None, scenario="normal"):
            if agent == "reconversion":
                # raise provoque volontairement une erreur pour tester sa gestion.
                raise ValueError("Recherche indisponible")
            if agent == "supervisor":
                # L'erreur du chercheur doit être transmise au superviseur.
                self.assertIn("error", dossiers["reconversion"])
                return {"recommendation": "Partielle"}, {"cost": .01}
            # None signifie « coût inconnu », et non « coût égal à zéro ».
            return {"summary": "Test"}, {"cost": None}

        run, events = self.run_workflow(stub)
        # Une recommandation reste disponible, mais elle est partielle.
        self.assertEqual(run["status"], "partial")
        self.assertFalse(run["cost_complete"])
        # La somme connue vaut 0,01 $, sans inventer le coût manquant.
        self.assertAlmostEqual(run["cost"], .01)
        # any(...) signifie « au moins un » : il faut une alerte d'erreur.
        self.assertTrue(any(e["type"] == "alert" and e["payload"]["code"] == "error" for e in events))
        # Ce résultat partiel ne doit pas servir à calculer une projection de coût.
        self.assertEqual(storage.metrics("demo")["projection_sample"], 0)

    # TEST 3 : les deux chercheurs échouent ; la synthèse doit être annulée.
    def test_two_failures_skip_supervisor(self):
        # Cette liste mémorise les agents effectivement appelés.
        calls = []

        # *args et **kwargs acceptent les autres arguments, inutiles pour ce scénario.
        async def stub(agent, *args, **kwargs):
            calls.append(agent)
            raise ValueError("Indisponible")

        run, events = self.run_workflow(stub)
        self.assertEqual(run["status"], "failed")
        # Aucun dossier disponible : on ne doit pas appeler le superviseur.
        self.assertNotIn("supervisor", calls)
        self.assertTrue(any(e["type"] == "agent_skipped" for e in events))
        # Aucun coût n'a été retourné : le résultat doit rester inconnu.
        self.assertIsNone(run["cost"])

    # TEST 4 : provoquer les trois types d'alertes, sans attendre 45 secondes.
    def test_all_alert_types(self):
        async def stub(agent, profile, dossiers=None, scenario="normal"):
            # Chaque appel simulé attend 0,035 seconde.
            await asyncio.sleep(.035)
            if agent == "reconversion":
                raise ValueError("Erreur de test")
            # 0,20 $ simulés dépassent le seuil de budget par défaut de 0,10 $.
            return {"summary": "Test", "recommendation": "Test"}, {"cost": .2}

        # Réduire temporairement le seuil de lenteur à 0,01 seconde.
        # Les appels de 0,035 seconde vont donc déclencher l'alerte rapidement.
        # La valeur habituelle est automatiquement rétablie à la fin du bloc.
        with patch.object(workflow, "SLOW_SECONDS", .01):
            # Le caractère _ indique qu'on n'utilise pas le deuxième résultat.
            run, _ = self.run_workflow(stub)
        # Les accolades créent un ensemble : on compare les TYPES d'alertes,
        # même si plusieurs agents ont chacun déclenché une alerte de lenteur.
        self.assertEqual({a["code"] for a in run["alerts"]}, {"slow", "budget", "error"})
        # Plusieurs dépassements ne doivent pas dupliquer l'alerte budget du workflow.
        self.assertEqual(len([a for a in run["alerts"] if a["code"] == "budget"]), 1)

    # TEST 5 : vérifier des routes API, le profil invalide et les exports.
    def test_endpoints_exports_and_validation(self):
        # Le premier « app » est le module app.py ; le second est l'objet FastAPI.
        with TestClient(app.app) as client:
            # Code HTTP 200 = la demande a réussi.
            self.assertEqual(client.get("/").status_code, 200)
            # Code HTTP 404 = cette mission n'existe pas.
            self.assertEqual(client.get("/api/runs/missing").status_code, 404)
            # Copier le profil en remplaçant sa situation par un espace vide.
            # post(...) reproduit l'envoi de données par le formulaire.
            invalid = client.post("/api/runs", json={"profile": dict(PROFILE, situation=" "), "mode": "demo"})
            # Code HTTP 422 = les données ne respectent pas la validation attendue.
            self.assertEqual(invalid.status_code, 422)
            # Un profil refusé ne doit créer aucune mission.
            self.assertEqual(len(storage.list_runs()), 0)
            exported = client.get("/api/workflow/export")
            self.assertEqual(exported.status_code, 200)
            # L'export doit contenir nos 3 agents. START et END sont des repères
            # techniques de LangGraph, on ne les compte pas comme des agents.
            self.assertEqual(len([n for n in exported.json()["graph"]["nodes"] if n["id"] not in ("__start__", "__end__")]), 3)
            # La table exportée doit proposer la colonne de corrélation.
            self.assertIn("correlation_id", client.get("/api/exports/runs.csv").text)
            # Vérification ciblée : la réponse health ne contient pas le préfixe
            # d'une clé OpenRouter. Ce contrôle porte uniquement sur cette réponse.
            self.assertNotIn("sk-or-", client.get("/api/health").text)

    # TEST 6 : simuler ce qui arrive à une mission active au redémarrage du serveur.
    def test_restart_keeps_history_marks_active_interrupted(self):
        # Créer une mission et une étape actives, sans les terminer.
        storage.create_run("restart", PROFILE, "demo", "test")
        storage.start_step("step", "restart", "evolution")
        # Cette fonction est aussi appelée au démarrage réel du serveur.
        # La rappeler simule ici la remise en état de la base au redémarrage ;
        # ce test ne redémarre pas réellement un processus serveur.
        storage.init_db()
        # Les enregistrements doivent toujours exister, avec le statut interrompu.
        self.assertEqual(storage.get_run("restart")["status"], "interrupted")
        self.assertEqual(storage.get_run("restart")["steps"][0]["status"], "interrupted")


# Si on exécute directement ce fichier, lancer ses tests avec un affichage détaillé.
# La pipeline les trouve aussi via : python -m unittest discover -s tests -v
if __name__ == "__main__":
    unittest.main(verbosity=2)
