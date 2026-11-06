"""Actual MCP stdio server. Each process exposes only one trusted role's tools."""
import json
import os

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from .state import CATALOG, CATALOG_SHA, Store, quote, runtime_path

ROLE_TOOLS = {"coordinator": {"create_decision"}, "researcher": {"list_plans", "publish_research"},
              "analyst": {"quote_plan", "publish_analysis"}, "reviewer": {"verify_decision", "publish_review"}}


def controlled(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def make_server(role: str, store: Store, bound_run: str | None):
    if role not in ROLE_TOOLS or (role != "coordinator" and not bound_run):
        raise ValueError("A valid role and bound run are required.")
    server = MCPServer("Support Council / " + role, version="1.0.0", log_level="ERROR",
                       instructions="Fictional support plans. Only this role's tools are available.")

    def require_run(run_id: str):
        if role != "coordinator" and run_id != bound_run:
            raise ValueError("This MCP process is scoped to another run.")
        return store.get(run_id)

    @server.resource("council://runs/{run_id}")
    def shared_state(run_id: str) -> str:
        """Read the versioned shared decision state, including earlier role handoffs."""
        try:
            return json.dumps(require_run(run_id))
        except ValueError as exc:
            raise ResourceError(str(exc)) from exc

    if role == "coordinator":
        @server.tool()
        def create_decision(seats: int, budget_cents: int, support_24h: bool, goal: str) -> dict:
            """Create immutable requirements; returns a new run ID and version zero."""
            return controlled(store.create, dict(seats=seats, budget_cents=budget_cents, support_24h=support_24h, goal=goal))

    if role == "researcher":
        @server.tool()
        def list_plans() -> dict:
            """Read the entire fictional catalog with its content hash."""
            require_run(bound_run)
            return {**CATALOG, "sha256": CATALOG_SHA}

        @server.tool()
        def publish_research(expected_version: int, plan_ids: list[str], note: str, note_source: str = "model") -> dict:
            """Publish catalog coverage and a research brief; valid only at version zero."""
            return controlled(store.publish, bound_run, role, expected_version, {"plan_ids": plan_ids, "note": note, "note_source": note_source})

    if role == "analyst":
        @server.tool()
        def quote_plan(plan_id: str) -> dict:
            """Compute exact monthly cents and eligibility from immutable requirements."""
            return controlled(quote, plan_id, require_run(bound_run)["requirements"])

        @server.tool()
        def publish_analysis(expected_version: int, recommended_plan: str | None, note: str, note_source: str = "model") -> dict:
            """Publish the cheapest eligible plan or null. Server independently verifies it."""
            return controlled(store.publish, bound_run, role, expected_version, {"recommended_plan": recommended_plan, "note": note, "note_source": note_source})

    if role == "reviewer":
        @server.tool()
        def verify_decision() -> dict:
            """Recompute all quotes and check the analyst's persisted decision."""
            return store.verify(bound_run)

        @server.tool()
        def publish_review(expected_version: int, approved: bool, note: str, note_source: str = "model") -> dict:
            """Publish the review at version two. Refused reviews remain needs_review."""
            if approved and not store.verify(bound_run)["valid"]:
                raise ToolError("Cannot approve an invalid decision.")
            return controlled(store.publish, bound_run, role, expected_version, {"approved": approved, "note": note, "note_source": note_source})

    return server


if __name__ == "__main__":
    make_server(os.environ["MCP_AGENT_ROLE"], Store(runtime_path(os.getenv("MCP_STATE_PATH"))),
                os.getenv("MCP_RUN_ID")).run(transport="stdio")
