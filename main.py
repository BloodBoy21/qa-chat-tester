# load_dotenv must run before any other import that reads os.getenv at module level

import asyncio
import os
from lib.agent_loop import run_from_json_file, run_agent
from loguru import logger
import sys


MAX_ANALYSIS_RETRIES = int(os.getenv("MAX_ANALYSIS_RETRIES", 3))
MAX_CONV_RETRIES = int(os.getenv("MAX_CONV_RETRIES", 3))
DEFAULT_MODEL = os.getenv("MODEL_NAME", "gemini-2.5-flash")

# Timeout per individual LLM call (seconds). Prevents a single hung API call
# from blocking the loop forever.
ITERATION_TIMEOUT = int(os.getenv("ITERATION_TIMEOUT", 120))

# Maximum total wall-clock time for one full run (conversation + analysis).
# When exceeded, the current iteration is skipped and analysis runs immediately.
RUN_TIMEOUT = int(os.getenv("RUN_TIMEOUT", 600))

# Timeout per individual analysis attempt (seconds).
ANALYSIS_TIMEOUT = int(os.getenv("ANALYSIS_TIMEOUT", 120))

MAX_CHAT_ITERATIONS = int(os.getenv("MAX_CHAT_ITERATIONS", 20))

# Max agents running concurrently within a single process.
# Prevents Gemini API rate-limit errors when batch_size is large.
MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", 3))

DEFAULT_ACCOUNT_ID = os.getenv("DEFAULT_ACCOUNT_ID", "1")


# ── CLI args ─────────────────────────────────────────────────────────────────


def _parse_args() -> dict:
    return dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)


def _validate_env():
    required = ["AGENT_URL", "AGENT_TOKEN"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


async def main():
    _validate_env()

    cli = _parse_args()
    model = cli.get("model", DEFAULT_MODEL)
    batch_size = int(cli.get("batch_size", 10))

    json_file_path = cli.get("json_file")
    if json_file_path:
        await run_from_json_file(
            json_file_path,
            batch_size=batch_size,
        )
        return

    context = cli.get("context", "No context provided.")
    user_id = cli.get("user_id", "default_user")
    logger.info(
        f"Starting agent | context={context} | user_id={user_id} | model={model}"
    )
    await run_agent(
        context=context,
        user_id=user_id,
        model=model,
    )


if __name__ == "__main__":
    asyncio.run(main())
