To enforce strict model routing between **`muse-spark-1.3-contributor`** (default handler) and **`muse-wonder-1.0`** (complex multi-step subagent), both operating at `max` effort, the architecture uses a deterministic **Task Router & Orchestrator** pattern.

In the **Aether** ecosystem, `muse-spark-1.3-contributor` handles high-frequency telemetry ingestion, active lens scoring, single-hop MCP lookups, and direct user queries. Whenever a task requires multi-stage planning, cross-role graph synthesis, or iterative tool execution, the orchestrator spawns an isolated subagent powered by `muse-wonder-1.0`.

---

## 1. Model Routing Matrix & Complexity Heuristics

The orchestrator evaluates every incoming request or background job against four structural triggers before dispatching:

| Routing Dimension | Default Tier (`muse-spark-1.3-contributor`) | Subagent Escalation Tier (`muse-wonder-1.0`) |
| --- | --- | --- |
| **Reasoning Effort** | `max` | `max` |
| **Step Count ($N_{\text{steps}}$)** | Atomic or linear (1 to 2 sequential actions) | Multi-step, branching, or cyclic (3 or more steps) |
| **Graph Traversal Depth** | 1-hop entity lookup or single-role lens scoring | Multi-hop cross-role synthesis or conflict resolution |
| **Tool / MCP Chaining** | Single tool call or static Context Capsule read | Dynamic tool discovery, code execution, or multi-system writes |
| **Aether Pipeline Role** | Telemetry normalization, entity extraction, fast MCP broker | Deep ontology restructuring, multi-agent planning, architectural synthesis |

---

## 2. Declarative Agent Task Plan (`agent_routing_plan.yaml`)

Drop this configuration into your agent orchestrator (e.g., LangGraph, AutoGen, or custom MCP router) to lock in the model assignments and escalation gates:

```yaml
version: "1.0"
orchestration_policy: "strict_tiered_delegation"

models:
  default_worker:
    model_id: "muse-spark-1.3-contributor"
    reasoning_effort: "max"
    temperature: 0.2
    role: "Primary responder, telemetry distiller, and single-step tool executor"
    
  complex_subagent:
    model_id: "muse-wonder-1.0"
    reasoning_effort: "max"
    temperature: 0.1
    role: "Autonomous subagent for multi-step decomposition, DAG execution, and deep synthesis"

routing_gate:
  default_target: "default_worker"
  escalation_target: "complex_subagent"
  escalation_triggers:
    - condition: "estimated_tool_calls >= 3"
    - condition: "requires_stateful_loop == true"
    - condition: "cross_role_graph_hops > 2"
    - condition: "task_type in ['architecture_design', 'multi_system_debug', 'ontology_reconciliation', 'code_refactoring_pipeline']"

task_execution_plan:
  - stage_id: "stage_1_triage_and_fast_path"
    assigned_model: "default_worker" # muse-spark-1.3-contributor (effort: max)
    tasks:
      - id: "ingest_and_classify"
        description: "Parse user prompt or OS telemetry event, query Active Lens, and compute task complexity score."
      - id: "fast_path_execution"
        condition: "escalation_triggers == false"
        description: "Execute single-step MCP tool call, synthesize Context Capsule, or return direct answer to user."

  - stage_id: "stage_2_subagent_delegation"
    assigned_model: "complex_subagent" # muse-wonder-1.0 (effort: max)
    condition: "escalation_triggers == true"
    tasks:
      - id: "dag_decomposition"
        description: "Break complex objective into an executable Directed Acyclic Graph (DAG) of subtasks with verification checkpoints."
      - id: "multi_step_execution"
        description: "Execute iterative tool calls, traverse multi-role Aether hypergraph edges, and resolve intermediate failures."
      - id: "state_consolidation"
        description: "Compile final artifact and generate a structured state diff for Aether's Ground Truth ledger."

  - stage_id: "stage_3_commit_and_delivery"
    assigned_model: "default_worker" # muse-spark-1.3-contributor (effort: max)
    tasks:
      - id: "graph_upsert"
        description: "Commit validated entity/edge updates from the subagent back into KùzuDB/SQLite."
      - id: "response_formatting"
        description: "Apply the Active Lens communication style and stream the final output to the client."

```

---

## 3. Runtime Dispatcher & Subagent Handoff (Python)

This dispatcher implements the routing logic in code, ensuring `muse-spark-1.3-contributor` handles the initial triage and all standard tasks at `max` effort, while seamlessly spawning `muse-wonder-1.0` at `max` effort when the task plan requires multi-step orchestration.

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Literal

@dataclass
class ModelConfig:
    model_id: str
    effort: Literal["low", "medium", "high", "max"] = "max"

# Enforce strict model definitions at max effort
SPARK_CONTRIBUTOR = ModelConfig(model_id="muse-spark-1.3-contributor", effort="max")
WONDER_SUBAGENT = ModelConfig(model_id="muse-wonder-1.0", effort="max")

@dataclass
class TaskPayload:
    prompt: str
    estimated_steps: int
    required_tools: List[str]
    cross_role_synthesis: bool = False
    context_capsule: Dict[str, Any] = field(default_factory=dict)

class AgentOrchestrator:
    def __init__(self):
        self.default_model = SPARK_CONTRIBUTOR
        self.subagent_model = WONDER_SUBAGENT

    def is_complex_multi_step(self, task: TaskPayload) -> bool:
        """Evaluates deterministic triggers for subagent escalation."""
        return (
            task.estimated_steps >= 3
            or len(task.required_tools) > 1
            or task.cross_role_synthesis
        )

    async def execute_task_plan(self, task: TaskPayload) -> Dict[str, Any]:
        # Step 1: Always use muse-spark-1.3-contributor (max) for fast-path or pre-flight triage
        if not self.is_complex_multi_step(task):
            return await self._run_spark_worker(task)

        # Step 2: Escalate complex multi-step workflows to muse-wonder-1.0 (max) subagent
        subagent_result = await self._spawn_wonder_subagent(task)

        # Step 3: Hand back to muse-spark-1.3-contributor (max) for final state commit
        return await self._finalize_with_spark(task, subagent_result)

    async def _run_spark_worker(self, task: TaskPayload) -> Dict[str, Any]:
        return {
            "executed_by": self.default_model.model_id,
            "effort": self.default_model.effort,
            "mode": "direct_execution",
            "output": f"Executed atomic/single-step task: '{task.prompt}'"
        }

    async def _spawn_wonder_subagent(self, task: TaskPayload) -> Dict[str, Any]:
        # Subagent builds a multi-step DAG and iterates over tools/graph hops
        dag_steps = [
            f"Step {i+1}: Execute {tool} with scoped context"
            for i, tool in enumerate(task.required_tools)
        ]
        return {
            "subagent_model": self.subagent_model.model_id,
            "effort": self.subagent_model.effort,
            "mode": "autonomous_multi_step_dag",
            "dag_trace": dag_steps,
            "synthesized_result": f"Completed {task.estimated_steps}-step synthesis for: '{task.prompt}'"
        }

    async def _finalize_with_spark(self, task: TaskPayload, subagent_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "primary_orchestrator": self.default_model.model_id,
            "primary_effort": self.default_model.effort,
            "delegated_subagent": subagent_data["subagent_model"],
            "subagent_effort": subagent_data["effort"],
            "trace": subagent_data["dag_trace"],
            "final_response": subagent_data["synthesized_result"]
        }

```

---

## 4. Execution Lifecycle in Practice

1. **Pre-Flight Triage (`muse-spark-1.3-contributor @ max`):**
Every incoming request hits `muse-spark-1.3-contributor` first. It pulls the active **Context Capsule** from Aether and classifies the task's structural complexity. If the request is a single-step task (e.g., *"Draft an email to the vendor"* or *"Extract entities from this terminal log"*), `muse-spark-1.3-contributor` completes it immediately in the same pass.
2. **Subagent Spawning (`muse-wonder-1.0 @ max`):**
If the task requires multi-step coordination (e.g., *"Correlate the ESXi VM power-on failure logs with recent host memory reservations, check if any maintenance windows conflict with Saturday's swim meet, and generate a remediation runbook"*), the router spawns `muse-wonder-1.0` at `max` effort. It receives a scoped state object, decomposes the prompt into a multi-step DAG, executes the necessary tool calls in parallel/sequence, and verifies intermediate outputs.
3. **State Commit & Formatting (`muse-spark-1.3-contributor @ max`):**
Once `muse-wonder-1.0` returns the verified multi-step artifact, `muse-spark-1.3-contributor` ingests the summary diff, updates Aether's graph edges in the background, and formats the final response to match your active persona's communication style.
