from dotenv import load_dotenv

import sys
from agents.user import UserAgent
from loguru import logger
import os
from utils.agent_runner import Agent as AgentRunner
from agents.analysis import AnalysisAgent
import asyncio
from utils.prompt_utils import extract_json_blocks

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
args = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)


async def main():
    context = args.get("context", "No context provided.")
    user_id = args.get("user_id", "default_user")
    model = args.get("model", MODEL_NAME)
    logger.info(
        f"Starting agent with context: {context}, user_id: {user_id}, model: {model}"
    )
    analysis_agent = AnalysisAgent(context=context, user_id=user_id, model=model)
    user_agent = UserAgent(
        context=context,
        user_id=user_id,
        model=model,
        sub_agents=[analysis_agent.Build()],
    )
    agent = user_agent.Build()
    runner = AgentRunner(user_id=user_id, agent=agent)
    await runner.generate(agent="UserAgent")
    conversation_loop = True
    previous_response = None
    try:
        while conversation_loop:
            res = await runner.from_text(
                "start" if previous_response is None else previous_response
            )
            if res is None or res.strip() == "" or res.strip() == "{}":
                logger.error("No response received from agent.")
                break
            res_json = extract_json_blocks(res)
            if res_json.get("conversation_end", False) or res_json.get("insights"):
                logger.info("Conversation ended by agent.")
                conversation_loop = False
                break
            previous_response = res
    except KeyboardInterrupt:
        logger.info("Conversation interrupted by user.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        logger.info("Ending conversation loop.")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
