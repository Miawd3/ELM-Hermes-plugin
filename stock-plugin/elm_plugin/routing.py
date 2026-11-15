"""Memory-aware agent routing: Hermes delegation backend `elm` (`delegation.backend: elm`).

You name your agents in config; each is a model route or one of your Hermes profiles:

    delegation:
      backend: elm
      backends:
        elm:
          default: quick                 # optional: used when nothing better is known
          learn: true                    # optional (default true): remember how routes went
          agents:
            quick: {description: "Small, fast tasks", model: deepseek-v4-flash, provider: deepseek}
            deep:  {description: "Hard reasoning", model: deepseek-v4-pro, provider: deepseek}
            coder: {description: "Code changes in my repos", profile: coder}

The model may name an agent per task. When it does not, ELM picks the agent that succeeded most
on similar earlier tasks (keyword overlap), else `default`, else the parent's own route.
ELM remembers only: which agent ran, a few keywords of the goal, success, duration - and only
for chats where ELM is on. Deleting a chat deletes its routing history. The model never sees
the history; only the agent names and descriptions you wrote.
"""
import re

from agent.delegation_provider import ROUTE_KEYS, DelegationProvider

from .stock_runtime import content_terms, needed_matches

BACKEND = 'elm'
AGENT_NAME = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')
MAX_AGENTS = 24
FAILURE_WEIGHT = 1.5  # a failure on similar work counts more than a success


def configured_agents(settings):
    """Valid agents from `delegation.backends.elm.agents`, by name. Invalid entries are skipped."""
    raw = settings.get('agents') if hasattr(settings, 'get') else None
    if not hasattr(raw, 'items'):
        return {}
    agents = {}
    for name, entry in sorted(raw.items(), key=lambda item: str(item[0])):
        if not (isinstance(name, str) and AGENT_NAME.match(name) and hasattr(entry, 'get')):
            continue
        route = {k: entry[k] for k in ROUTE_KEYS if k in entry and k != 'label'}
        if not route:
            continue
        description = entry.get('description') if isinstance(entry.get('description'), str) else ''
        agents[name] = {'route': route, 'description': ' '.join(description.split())[:200]}
        if len(agents) >= MAX_AGENTS:
            break
    return agents


def score_agents(terms, history, names):
    """Sum of keyword overlap with past outcomes per agent (successes +, failures -)."""
    scores = {}
    if not terms:
        return scores
    wanted, needed = set(terms), max(1, min(2, needed_matches(terms)))
    for agent, past_terms, ok in history:
        if agent not in names:
            continue
        overlap = len(wanted & set(past_terms))
        if overlap >= needed:
            scores[agent] = scores.get(agent, 0.0) + (overlap if ok else -FAILURE_WEIGHT * overlap)
    return scores


class ElmDelegationProvider(DelegationProvider):
    def __init__(self, store_factory=None):
        self._store_factory = store_factory  # tests inject a Store; real use: this profile's ELM store
        self._store = None

    @property
    def name(self):
        return BACKEND

    @property
    def display_name(self):
        return 'ELM (memory-aware)'

    @property
    def summary(self):
        return 'Your named agents (models or profiles); ELM picks the one that did best on similar past tasks.'

    def store(self):
        if self._store is None:
            from .stock_store import Store
            self._store = self._store_factory() if self._store_factory else Store()
        return self._store

    def task_parameters(self, config):
        agents = configured_agents(self.settings(config))
        if not agents:
            return {}
        return {'agent': {'type': 'string', 'enum': sorted(agents),
                          'description': 'Which of the listed agents runs this task. Leave it out to let ELM choose from past results.'}}

    def description(self, config):
        agents = configured_agents(self.settings(config))
        if not agents:
            return ''
        lines = [f'- {name}: {info["description"] or "(no description)"}' for name, info in agents.items()]
        return 'Agents for `agent` (ELM routing):\n' + '\n'.join(lines)

    def _choose(self, goal, agents, settings):
        if settings.get('learn', True) is not False:
            try:
                scores = score_agents(content_terms(goal), self.store().route_history(), set(agents))
            except Exception:
                scores = {}
            best = max(sorted(scores), key=lambda a: scores[a], default=None)
            if best is not None and scores[best] > 0:
                return best, 'history'
        default = settings.get('default')
        if isinstance(default, str) and default in agents:
            return default, 'default'
        return None, 'parent'

    def route_task(self, task, config):
        settings = self.settings(config)
        agents = configured_agents(settings)
        parent_route = {k: v for k, v in config.items() if k in ROUTE_KEYS and k != 'service_tier'}
        if not agents:
            return parent_route
        goal = task.get('goal') if isinstance(task.get('goal'), str) else ''
        choice, chosen_by = task.get('agent'), 'model'
        if choice not in agents:
            choice, chosen_by = self._choose(goal, agents, settings)
        if choice is None:
            return dict(parent_route, label='ELM: parent model')
        route = dict(agents[choice]['route'])
        route['label'] = f'ELM: {choice}' + {'history': ' (past results)', 'default': ' (default)'}.get(chosen_by, '')
        if settings.get('learn', True) is not False:
            try:
                self.store().route_pending(goal, choice, chosen_by)
            except Exception:
                pass  # routing never fails because memory is unavailable
        return route
