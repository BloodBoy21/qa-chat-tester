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

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
args = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)


def generate_run_id():
    return str(uuid.uuid4())


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
    total_batches = (len(data) + batch_size - 1) // batch_size
    start = datetime.datetime.now()
    logger.info(f"Starting batch processing at {start.isoformat()}")
    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        logger.info(f"Processing batch {i // batch_size + 1} of {total_batches}")

        tasks = [
            run_agent(
                context=turn,
                user_id=turn.get("user_id", "default_user"),
                model=turn.get("model", MODEL_NAME),
            )
            for turn in batch
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(
            f"Finished processing batch {i // batch_size + 1} of {total_batches}"
        )
        logger.info("Starting next batch...")
        logger.info(f"Current time: {datetime.datetime.now().isoformat()}")
        logger.info("-" * 50)

    logger.info("Finished processing all batches.")
    total_time = (datetime.datetime.now() - start).total_seconds()
    total_time_formatted = str(datetime.timedelta(seconds=total_time))
    logger.info(
        f"Total processing time: {total_time_formatted}"
    )  # human readable format
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


async def run_analysis_agent(agent, run_id: str, user_id: str, retries=3):
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


async def run_agent(context: str, user_id: str, model: str, batch=None):
    log_db = LogDB()
    run_id = generate_run_id()
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
    try:
        max_iterations = int(args.get("max_iterations", 30))
        while conversation_loop:

            res = await runner.from_text(
                "start" if previous_response is None else previous_response
            )
            if res is None or res.strip() == "" or res.strip() == "{}":
                logger.error("No response received from agent.")
                break
            res_json = extract_json_blocks(res)
            if (
                res_json.get("conversation_end", False)
                or res_json.get("insights")
                or "insights" in res
            ):
                logger.info("Conversation ended by agent.")
                conversation_loop = False
                break
            previous_response = res
            max_iterations -= 1
            if max_iterations <= 0:
                logger.info("Maximum iterations reached.")
                break

    except KeyboardInterrupt:
        logger.info("Conversation interrupted by user.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if batch is not None:
            logger.info(
                f"Finished processing batch for user_id: {user_id}, batch: {batch}"
            )
        has_analysis = log_db.insight_exists_by_run_id(run_id)
        if not has_analysis:
            logger.warning(
                f"No analysis found for run_id {run_id}. This may indicate an issue with the conversation flow or that the AnalysisAgent was not called properly."
            )
            await run_analysis_agent(analysis_agent, run_id, user_id)

        logger.info("Ending conversation loop.")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
