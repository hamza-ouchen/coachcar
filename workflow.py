"""Three genuine LangGraph nodes with parallel research and a join."""
import asyncio
import os
from dataclasses import dataclass, field
from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph, START, END

import provider
import storage
import operations

AGENTS = {"evolution": "Évolution", "reconversion": "Reconversion", "supervisor": "Superviseur"}
SLOW_SECONDS = float(os.getenv("SLOW_STEP_SECONDS", "45"))
BUDGET_USD = float(os.getenv("BUDGET_ALERT_USD", "0.10"))


class State(TypedDict, total=False):
    profile: dict
    evolution: dict
    reconversion: dict
    supervisor: dict


@dataclass
class Execution:
    run_id: str
    demo: bool = False
    scenario: str = "normal"
    started: float = field(default_factory=perf_counter)

    def elapsed(self):
        return round((perf_counter() - self.started) * 1000, 2)

    def event(self, kind, payload=None, agent=None, step_id=None):
        return storage.emit(self.run_id, kind, self.elapsed(), payload, agent, step_id)

    def alert(self, agent, code, message, step_id=None):
        if storage.add_alert(self.run_id, agent, code, message):
            self.event("alert", {"code": code, "message": message}, agent, step_id)

    async def monitor_slow(self, agent, step_id):
        threshold = 2.5 if self.demo and self.scenario == "alerts" else SLOW_SECONDS
        await asyncio.sleep(threshold)
        self.alert(agent, "slow", f"{AGENTS[agent]} dépasse le seuil de {threshold:g} secondes.", step_id)

    async def node(self, agent, state):
        # Check again at every node boundary: a pause must also prevent handoffs.
        if operations.get_state()["paused"]:
            raise asyncio.CancelledError("Arrêt d'urgence actif")
        if agent == "supervisor" and all(state.get(a, {}).get("error") for a in ("evolution", "reconversion")):
            self.event("agent_skipped", {"message": "Aucun dossier exploitable : synthèse annulée."}, agent)
            return {agent: {"error": "Les deux recherches ont échoué."}}
        step_id = str(uuid4())
        storage.start_step(step_id, self.run_id, agent)
        self.event("agent_started", {"message": "Comparaison des dossiers" if agent == "supervisor" else "Recherche et analyse du marché", "demo": self.demo}, agent, step_id)
        started = perf_counter()
        monitor = asyncio.create_task(self.monitor_slow(agent, step_id))
        try:
            dossiers = {a: state.get(a, {}) for a in ("evolution", "reconversion")} if agent == "supervisor" else None
            call = (provider.demo_agent(agent, state["profile"], dossiers, self.scenario) if self.demo else
                    provider.call_agent(agent, state["profile"], dossiers))
            dossier, usage = await asyncio.wait_for(call, timeout=provider.TIMEOUT)
            duration = round((perf_counter() - started) * 1000, 2)
            storage.finish_step(step_id, "completed", duration, dossier, usage)
            self.event("agent_completed", {"message": "Dossier prêt" if agent != "supervisor" else "Recommandation prête", "duration_ms": duration, "usage": usage, "source_count": len(dossier.get("sources", [])), "web_verified": dossier.get("web_verified")}, agent, step_id)
            if agent != "supervisor":
                self.event("handoff", {"from": agent, "to": "supervisor", "message": "Dossier transmis au superviseur", "title": dossier.get("title", "Dossier")}, agent, step_id)
            return {agent: dossier}
        except asyncio.CancelledError:
            duration = round((perf_counter() - started) * 1000, 2)
            storage.finish_step(step_id, "cancelled", duration, error="Étape interrompue localement.")
            self.event("agent_cancelled", {"message": "Étape interrompue par l'arrêt du traitement", "duration_ms": duration}, agent, step_id)
            raise
        except Exception as exc:
            error = provider.friendly_error(exc)
            duration = round((perf_counter() - started) * 1000, 2)
            usage = getattr(exc, "usage", None)
            storage.finish_step(step_id, "failed", duration, usage=usage, error=error)
            self.event("agent_failed", {"message": error, "duration_ms": duration, "usage": usage}, agent, step_id)
            self.alert(agent, "error", error, step_id)
            return {agent: {"error": error}}
        finally:
            monitor.cancel()
            try:
                await monitor
            except asyncio.CancelledError:
                pass
            # A malformed response can still have been billed by the provider.
            run = storage.get_run(self.run_id)
            if run["cost"] is not None and run["cost"] > BUDGET_USD:
                self.alert("workflow", "budget", f"Coût {'simulé' if self.demo else 'connu'} : ${run['cost']:.4f}, au-dessus du seuil de ${BUDGET_USD:.2f}.")


def build_graph(ctx):
    graph = StateGraph(State)

    async def evolution(state):
        return await ctx.node("evolution", state)

    async def reconversion(state):
        return await ctx.node("reconversion", state)

    async def supervisor(state):
        return await ctx.node("supervisor", state)

    graph.add_node("evolution", evolution)
    graph.add_node("reconversion", reconversion)
    graph.add_node("supervisor", supervisor)
    graph.add_edge(START, "evolution")
    graph.add_edge(START, "reconversion")
    graph.add_edge(["evolution", "reconversion"], "supervisor")
    graph.add_edge("supervisor", END)
    return graph.compile()


async def execute(run_id, profile, demo=False, scenario="normal"):
    ctx = Execution(run_id, demo, scenario)
    ctx.event("run_started", {"message": "Mission lancée", "mode": "demo" if demo else "live"})
    try:
        state = await build_graph(ctx).ainvoke({"profile": profile})
        result = state.get("supervisor", {})
        failed = result.get("error")
        partial = any(state.get(a, {}).get("error") for a in ("evolution", "reconversion"))
        status = "failed" if failed else "partial" if partial else "completed"
        storage.finish_run(run_id, status, ctx.elapsed(), None if failed else result, failed)
        ctx.event("run_failed" if failed else "run_completed", {"status": status, "message": failed or ("Recommandation partielle disponible" if partial else "Votre orientation est prête")})
    except asyncio.CancelledError:
        message = "Traitement annulé localement ; les frais déjà engagés auprès du fournisseur peuvent subsister."
        storage.finish_run(run_id, "cancelled", ctx.elapsed(), error=message)
        ctx.event("run_cancelled", {"status": "cancelled", "message": message})
        raise
    except Exception as exc:
        error = provider.friendly_error(exc)
        storage.finish_run(run_id, "failed", ctx.elapsed(), error=error)
        ctx.alert("workflow", "error", error)
        ctx.event("run_failed", {"status": "failed", "message": error})


def export_workflow():
    graph = build_graph(Execution("export"))
    return {"name": "Cap Avenir", "version": operations.version(), "framework": "LangGraph", "model": provider.MODEL,
            "description": "Deux recherches parallèles puis un superviseur ; état partagé et événements corrélés.",
            "graph": graph.get_graph().to_json(),
            "agents": AGENTS, "alerts": {"slow_seconds": SLOW_SECONDS, "budget_usd": BUDGET_USD, "error": "Échec d'une étape"},
            "mermaid": graph.get_graph().draw_mermaid(),
            "operations": {"approval": "Image Docker exacte approuvée avant déploiement via le gestionnaire local", "kill_switch": "Pause persistante et annulation locale", "rollback": "Retour à une image précédemment déployée", "incidents": "Mode démonstration uniquement"}}
