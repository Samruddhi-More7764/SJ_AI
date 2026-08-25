"""Wire Claude (via AI Credits) + read-only Postgres to the StockJarvis agent."""

from __future__ import annotations

from datetime import date

# #region agent log
import json
import sys
import time
from importlib.util import find_spec
from pathlib import Path as _DbgPath

def _agent_dbg(hypothesis_id: str, message: str, data: dict) -> None:
    payload = {
        "sessionId": "be79e4",
        "runId": "post-fix",
        "hypothesisId": hypothesis_id,
        "location": "app/agent.py:import",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with _DbgPath("/Users/samruddhimore/Desktop/t-to-sql/.cursor/debug-be79e4.log").open("a") as _f:
        _f.write(json.dumps(payload) + "\n")

_spec = find_spec("vanna")
_agent_dbg(
    "A",
    "vanna find_spec before import",
    {
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "path_head": sys.path[:8],
        "spec_origin": None if _spec is None else getattr(_spec, "origin", None),
        "spec_sublocs": None if _spec is None else list(_spec.submodule_search_locations or []),
    },
)
try:
    from vanna import Agent, AgentConfig
    import vanna as _vanna_mod

    _agent_dbg(
        "C",
        "vanna import succeeded",
        {
            "vanna_file": getattr(_vanna_mod, "__file__", None),
            "has_agent": hasattr(_vanna_mod, "Agent"),
        },
    )
except Exception as _exc:
    try:
        import vanna as _vanna_mod

        _vfile = getattr(_vanna_mod, "__file__", None)
        _vnames = [n for n in dir(_vanna_mod) if not n.startswith("_")][:40]
    except Exception as _inner:
        _vfile = None
        _vnames = [type(_inner).__name__, str(_inner)[:200]]
    _agent_dbg(
        "A",
        "vanna import failed",
        {
            "err_type": type(_exc).__name__,
            "err": str(_exc)[:300],
            "vanna_file": _vfile,
            "vanna_names": _vnames,
        },
    )
    raise
# #endregion

from vanna.core.agent.config import DEFAULT_UI_FEATURES, UiFeature, UiFeatures
from vanna.core.registry import ToolRegistry
from vanna.core.system_prompt import DefaultSystemPromptBuilder
from vanna.integrations.local import FileSystemConversationStore, LocalFileSystem
from vanna.integrations.local.agent_memory import DemoAgentMemory

from app.charts import FilingsVisualizeDataTool
from app.clarify import ask_clarify, load_company_catalog
from app.config import database_url_from_env, llm_settings_from_env
from app.db_cache import PostgresAnswerCache
from app.hooks import CacheWriteHook, SlotContextEnhancer
from app.llm import StockJarvisLlmService
from app.prompt import build_system_prompt
from app.sql import FilingsRunSqlTool, ReadOnlyPostgresRunner
from app.users import NoAuthUserResolver
from app.workflow import StockJarvisWorkflowHandler

MAX_TOOL_ITERATIONS = 3
WELCOME = (
    "Ask the filings — figures from NSE XML in this database. "
    "If the filings do not contain the answer, I will say so."
)


def create_agent() -> Agent:
    database_url = database_url_from_env()
    if not database_url:
        raise RuntimeError("Set DATABASE_URL or PGHOST/PGDATABASE/PGUSER.")

    api_key, base_url, model = llm_settings_from_env()
    prompt = build_system_prompt(today=date.today().isoformat())
    catalog = load_company_catalog(database_url)
    cache = PostgresAnswerCache(database_url)
    llm = StockJarvisLlmService(model=model, api_key=api_key, base_url=base_url)

    async def clarify_fn(message, state, history, user):
        return await ask_clarify(llm, message, state, history, user)

    file_system = LocalFileSystem(working_directory="./query_results")
    tools = ToolRegistry()
    tools.register_local_tool(
        FilingsRunSqlTool(
            sql_runner=ReadOnlyPostgresRunner(connection_string=database_url),
            file_system=file_system,
        ),
        access_groups=[],
    )
    tools.register_local_tool(
        FilingsVisualizeDataTool(file_system=file_system),
        access_groups=[],
    )

    ui_access = {key: list(groups) for key, groups in DEFAULT_UI_FEATURES.items()}
    ui_access[UiFeature.UI_FEATURE_SHOW_TOOL_NAMES] = ["admin"]

    return Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=NoAuthUserResolver(),
        agent_memory=DemoAgentMemory(),
        conversation_store=FileSystemConversationStore(base_dir="./conversations"),
        config=AgentConfig(
            stream_responses=True,
            max_tool_iterations=MAX_TOOL_ITERATIONS,
            ui_features=UiFeatures(feature_group_access=ui_access),
        ),
        system_prompt_builder=DefaultSystemPromptBuilder(base_prompt=prompt),
        workflow_handler=StockJarvisWorkflowHandler(
            catalog=catalog,
            cache=cache,
            welcome_message=WELCOME,
            clarify_fn=clarify_fn,
        ),
        llm_context_enhancer=SlotContextEnhancer(),
        lifecycle_hooks=[CacheWriteHook(cache)],
    )
