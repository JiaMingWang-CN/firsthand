"""Minimal Reddit simulation with distinct per-agent action sets."""

import argparse
import asyncio
import os
import sqlite3
from pathlib import Path

from core.runtime import error_summary, require_capabilities, settings, thinking_body, write_json


async def probe_discussion(config, run_dir):
    # OASIS creates ./log on import. Keep all runtime artifacts inside this run.
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    original_cwd = Path.cwd()
    os.chdir(run_dir)
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    import oasis
    from oasis import ActionType, AgentGraph, LLMAction, ManualAction, SocialAgent, UserInfo

    result = {"passed": False, "steps": 0}
    env = None
    try:
        model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=config["model"], url=config["base_url"], api_key=config["api_key"],
            model_config_dict={"temperature": 0, "max_tokens": 512, "extra_body": thinking_body(config)},
            timeout=60, max_retries=0,
        )
        graph = AgentGraph()
        allowed = {
            "poster": [ActionType.CREATE_POST, ActionType.CREATE_COMMENT, ActionType.REFRESH, ActionType.DO_NOTHING],
            "lurker": [ActionType.REFRESH, ActionType.DO_NOTHING],
        }
        agents = {}
        for index, (role, actions) in enumerate(allowed.items()):
            agent = SocialAgent(
                agent_id=index, user_info=UserInfo(user_name=role, name=role, description=
                    "Phase-zero test user who already used a product. Read the feed and use exactly one of your available tools.",
                    profile=None, recsys_type="reddit"),
                agent_graph=graph, model=model, available_actions=actions, max_iteration=1,
            )
            graph.add_agent(agent)
            agents[role] = agent
        tool_sets = {role: sorted(tool.func.__name__ for tool in agent.action_tools) for role, agent in agents.items()}
        result["action_tools"] = tool_sets
        result["action_sets_verified"] = all(set(tool_sets[role]) == {a.value for a in actions} for role, actions in allowed.items())
        if not result["action_sets_verified"]:
            raise AssertionError("OASIS exposed unexpected actions")
        database = run_dir / "oasis.db"
        if database.exists():
            raise FileExistsError("Use a fresh run directory; existing simulation must be preserved")
        env = oasis.make(agent_graph=graph, platform=oasis.DefaultPlatformType.REDDIT, database_path=str(database))
        await asyncio.wait_for(env.reset(), timeout=60)
        await asyncio.wait_for(env.step({agents["poster"]: ManualAction(
            action_type=ActionType.CREATE_POST, action_args={"content": "I tried the product. This is a phase-zero seed post."}
        )}), timeout=60)
        result["steps"] += 1
        with sqlite3.connect(database) as connection:
            result["manual_post_count"] = connection.execute("SELECT COUNT(*) FROM post").fetchone()[0]
            seed_trace_count = connection.execute("SELECT COUNT(*) FROM trace").fetchone()[0]
        await asyncio.wait_for(env.step({agent: LLMAction() for agent in agents.values()}), timeout=180)
        result["steps"] += 1
        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            result["traces"] = [dict(row) for row in connection.execute("SELECT * FROM trace ORDER BY rowid")]
        lurker_traces = [row for row in result["traces"] if row["user_id"] == 1]
        result["lurker_read_only"] = all(row["action"] in {"sign_up", "refresh", "do_nothing"} for row in lurker_traces)
        # OASIS refreshes each feed before calling the LLM; that observation alone
        # must not count as proof of a successful model tool call.
        llm_traces = {}
        for index, role in enumerate(allowed):
            rows = [row for row in result["traces"][seed_trace_count:] if row["user_id"] == index]
            llm_traces[role] = rows[1:] if rows and rows[0]["action"] == "refresh" else []
        result["llm_actions_verified"] = all(
            rows and all(row["action"] in {a.value for a in allowed[role]} for row in rows)
            for role, rows in llm_traces.items()
        )
        result["passed"] = result["manual_post_count"] == 1 and result["lurker_read_only"] and result["llm_actions_verified"]
    except Exception as error:
        result["error"] = error_summary(error, run_dir)
    finally:
        if env and hasattr(env, "platform_task"):
            try:
                await asyncio.wait_for(env.close(), timeout=15)
                result["closed"] = True
            except Exception as error:
                result["close_error"] = error_summary(error, run_dir)
                result["passed"] = False
                env.platform_task.cancel()
        os.chdir(original_cwd)
        write_json(run_dir / "oasis_result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    config = settings()
    try:
        require_capabilities(args.run_dir, config)
        result = asyncio.run(probe_discussion(config, args.run_dir))
    except Exception as error:
        result = {"passed": False, "error": error_summary(error, args.run_dir)}
        write_json(args.run_dir / "oasis_result.json", result)
    print("OASIS: " + ("PASS" if result["passed"] else "FAIL"))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
