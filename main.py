from dotenv import load_dotenv

import sys
from agents.user import UserAgent
from loguru import logger
import os
from utils.agent_runner import Agent as AgentRunner
from agents.analysis import AnalysisAgent
import asyncio
from utils.prompt_utils import extract_json_blocks
import json
import datetime
import uuid
from db.sql import LogDB

MAX_ANALYSIS_RETRIES = int(os.getenv("MAX_ANALYSIS_RETRIES", 5))
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
args = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)


def generate_run_id():
    return str(uuid.uuid4())


def fmt_duration(seconds: float) -> str:
    """Format seconds into human-readable duration string."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.0f}s"


async def run_from_json_file(file_path: str):
    data = []
    batch_size = int(args.get("batch_size", 10))
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read JSON file: {e}")
        return "Error reading JSON file."
    if not isinstance(data, list):
        logger.error("JSON file must contain a list of conversation turns.")
        return "JSON file must contain a list of conversation turns."

    total_items = len(data)
    total_batches = (total_items + batch_size - 1) // batch_size
    process_start = datetime.datetime.now()

    logger.info("=" * 60)
    logger.info(f"PROCESS START")
    logger.info(f"  Total items:  {total_items}")
    logger.info(f"  Batch size:   {batch_size}")
    logger.info(f"  Total batches: {total_batches}")
    logger.info(f"  Started at:   {process_start.isoformat()}")
    logger.info("=" * 60)

    batch_timings = []

    for i in range(0, total_items, batch_size):
        batch = data[i : i + batch_size]
        batch_num = i // batch_size + 1
        batch_start = datetime.datetime.now()

        logger.info("-" * 60)
        logger.info(
            f"BATCH {batch_num}/{total_batches} | "
            f"Items {i + 1}-{min(i + batch_size, total_items)} of {total_items} | "
            f"Size: {len(batch)}"
        )

        tasks = [
            run_agent(
                context=turn,
                user_id=turn.get("user_id", "default_user"),
                model=turn.get("model", MODEL_NAME),
                batch=batch_num,
                item_index=i + idx,
                total_items=total_items,
            )
            for idx, turn in enumerate(batch)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_elapsed = (datetime.datetime.now() - batch_start).total_seconds()
        batch_timings.append(batch_elapsed)

        # Count successes/failures in this batch
        failures = sum(1 for r in results if isinstance(r, Exception))
        successes = len(results) - failures

        process_elapsed = (datetime.datetime.now() - process_start).total_seconds()
        avg_per_batch = process_elapsed / batch_num
        remaining_batches = total_batches - batch_num
        eta_seconds = avg_per_batch * remaining_batches

        logger.info(
            f"BATCH {batch_num}/{total_batches} DONE | "
            f"Duration: {fmt_duration(batch_elapsed)} | "
            f"OK: {successes} | FAIL: {failures}"
        )
        if remaining_batches > 0:
            logger.info(
                f"  Progress: {batch_num}/{total_batches} batches | "
                f"Elapsed: {fmt_duration(process_elapsed)} | "
                f"ETA remaining: ~{fmt_duration(eta_seconds)}"
            )

        for idx, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"  Item {i + idx + 1} failed with error: {r}")

    # ── Process summary ─────────────────────────────────────────
    process_elapsed = (datetime.datetime.now() - process_start).total_seconds()

    logger.info("=" * 60)
    logger.info(f"PROCESS COMPLETE")
    logger.info(f"  Total duration:     {fmt_duration(process_elapsed)}")
    logger.info(f"  Total items:        {total_items}")
    logger.info(
        f"  Avg per item:       {fmt_duration(process_elapsed / total_items) if total_items > 0 else 'N/A'}"
    )
    logger.info(f"  Total batches:      {total_batches}")
    if batch_timings:
        logger.info(f"  Fastest batch:      {fmt_duration(min(batch_timings))}")
        logger.info(f"  Slowest batch:      {fmt_duration(max(batch_timings))}")
        logger.info(
            f"  Avg batch duration: {fmt_duration(sum(batch_timings) / len(batch_timings))}"
        )
    logger.info(f"  Finished at:        {datetime.datetime.now().isoformat()}")
    logger.info("=" * 60)

    return "Batch processing completed."


async def main():
    context = args.get("context", "No context provided.")
    user_id = args.get("user_id", "default_user")
    model = args.get("model", MODEL_NAME)
    json_file_path = args.get("json_file")
    if json_file_path:
        return await run_from_json_file(json_file_path)
    logger.info(
        f"Starting agent with context: {context}, user_id: {user_id}, model: {model}"
    )
    await run_agent(context=context, user_id=user_id, model=model)


async def run_analysis_agent(
    agent, run_id: str, user_id: str, retries=MAX_ANALYSIS_RETRIES
):
    try:
        log_db = LogDB()
        runner = AgentRunner(user_id=user_id, agent=agent)
        await runner.generate()
        session_id = log_db.get_session_id_by_run_id(run_id)
        if session_id is None:
            logger.error(
                f"No session_id found for run_id {run_id}. Cannot run AnalysisAgent."
            )
            return
        await runner.from_text(session_id)
        await asyncio.sleep(5)  # Wait for insights to be saved
        exits_analysis = log_db.insight_exists_by_run_id(run_id)
        if not exits_analysis:
            raise Exception("AnalysisAgent did not save any insights.")
        logger.info(f"AnalysisAgent completed successfully for run_id {run_id}.")
    except Exception as e:
        logger.error(f"Error running AnalysisAgent: {e}")
        if retries > 0:
            logger.info(f"Retrying AnalysisAgent. Attempts left: {retries}")
            await run_analysis_agent(agent, run_id, user_id, retries - 1)
        else:
            logger.error("Max retries reached for AnalysisAgent. Aborting.")


async def run_agent(
    context: str,
    user_id: str,
    model: str,
    batch=None,
    item_index: int = None,
    total_items: int = None,
):
    log_db = LogDB()
    run_id = generate_run_id()
    item_label = (
        f"[Batch {batch} | Item {item_index + 1}/{total_items}]"
        if item_index is not None
        else "[Single]"
    )
    item_start = datetime.datetime.now()

    logger.info(f"{item_label} Starting agent | user_id={user_id} | model={model}")

    analysis_agent = AnalysisAgent(context=context, user_id=user_id, model=model)
    analysis_agent.set_run_id(run_id)
    analysis_agent = analysis_agent.Build()
    user_agent = UserAgent(
        context=context,
        user_id=user_id,
        model=model,
        sub_agents=[analysis_agent],
    )
    user_agent.set_run_id(run_id)
    agent = user_agent.Build()
    runner = AgentRunner(user_id=user_id, agent=agent)
    await runner.generate()
    conversation_loop = True
    previous_response = None
    iteration_count = 0
    try:
        max_iterations = int(args.get("max_iterations", 30))
        while conversation_loop:
            iteration_count += 1
            iter_start = datetime.datetime.now()

            res = await runner.from_text(
                "start" if previous_response is None else previous_response
            )

            iter_elapsed = (datetime.datetime.now() - iter_start).total_seconds()
            logger.debug(
                f"{item_label} Iteration {iteration_count} | "
                f"Duration: {fmt_duration(iter_elapsed)}"
            )

            if res is None or res.strip() == "" or res.strip() == "{}":
                logger.error(
                    f"{item_label} No response at iteration {iteration_count}."
                )
                break
            res_json = extract_json_blocks(res)
            if (
                res_json.get("conversation_end", False)
                or res_json.get("insights")
                or "insights" in res
            ):
                logger.info(
                    f"{item_label} Conversation ended by agent at iteration {iteration_count}."
                )
                conversation_loop = False
                break
            previous_response = res
            max_iterations -= 1
            if max_iterations <= 0:
                logger.info(
                    f"{item_label} Max iterations reached ({iteration_count} total)."
                )
                break
            await asyncio.sleep(
                1
            )  # Small delay between iterations to prevent tight loop

    except KeyboardInterrupt:
        logger.info(f"{item_label} Interrupted by user.")
    except Exception as e:
        logger.error(f"{item_label} Error at iteration {iteration_count}: {e}")
    finally:
        has_analysis = log_db.insight_exists_by_run_id(run_id)
        if not has_analysis:
            logger.warning(
                f"{item_label} No analysis for run_id {run_id}. Running AnalysisAgent fallback."
            )
            await run_analysis_agent(analysis_agent, run_id, user_id)

        item_elapsed = (datetime.datetime.now() - item_start).total_seconds()
        logger.info(
            f"{item_label} DONE | "
            f"Iterations: {iteration_count} | "
            f"Duration: {fmt_duration(item_elapsed)} | "
            f"Avg/iteration: {fmt_duration(item_elapsed / max(iteration_count, 1))}"
        )


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
