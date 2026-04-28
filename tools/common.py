from bson.codec_options import DEFAULT
import os
import json
import asyncio
import concurrent.futures
from typing import Dict

import requests as r
from loguru import logger

from db.sql import LogDB
from utils.prompt_utils import extract_json_blocks

SERVICE_URL = os.getenv("AGENT_URL", "")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "120"))
_TOKEN = os.getenv("AGENT_TOKEN", "")

_http_executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)

DEFAULT_ACCOUNT_ID = os.getenv("DEFAULT_ACCOUNT_ID", "default_account")


def clean_response(response_dict: dict) -> dict:
    if isinstance(response_dict, str):
        response_dict = json.loads(response_dict)

    clean = {**response_dict}
    if "traces" in clean:
        for trace in clean["traces"]:
            payload = trace.get("payload", {})
            content = payload.get("content", {})
            if isinstance(content, dict):
                for part in content.get("parts", []):
                    part.pop("thoughtSignature", None)
    return clean


def _http_post(data: dict) -> dict:
    response = r.post(
        url=f"{SERVICE_URL}/chat",
        json=data,
        headers={"Authorization": f"Bearer {_TOKEN}"},
        timeout=REQUEST_TIMEOUT,
    )
    return response.json()


def send_to_agent(
    message: str,
    user_id: str = "default_user",
    images: list = None,
    attachments: list = None,
    campaigns: list = None,
    bot_message: str = "",
    account_id: str = DEFAULT_ACCOUNT_ID,
    session_id: str = "",
    session_backend: str = "redis",
    persist_session: bool = True,
    run_id: str = "",
    pre_session_id: str = "",
    scenario_group_id: str = "",
    scenario: str = "",
    *args,
    **kwargs,
) -> dict:
    """
    Send a message to the agent and get the response.
    Args:
        message (str): The message to send to the agent.
        user_id (str): The ID of the user sending the message.
        images (list[str]): A list of image URLs to include in the message.
        attachments (list[dict[str, str]]): A list of attachment dicts to include.
        campaigns (list[dict[str, str]]): A list of campaign dicts to include in the context.
        bot_message (str): Previous message from the bot to simulate in the current turn if hsm is being used.
        account_id (str): The ID of the account associated with the message.
        session_id (str): The ID of the session for maintaining context.
        session_backend (str): The backend to use for session management.
        persist_session (bool): Whether to persist the session after processing.
        scenario_group_id (str): The ID of the scenario group.
        scenario (str): The name of the scenario being executed.

    Returns:
        dict: The response from the agent.
    """
    try:
        images = images or []
        attachments = attachments or []
        campaigns = campaigns or []

        data = {
            "account_id": account_id,
            "user_id": user_id,
            "text": message,
            "images": images,
            "attachments": attachments,
            "session_id": session_id,
            "session_backend": session_backend,
            "persist_session": persist_session,
            "campaigns": campaigns,
            "bot_message": {
                "text": bot_message or "",
                "is_hsm": bool(len(campaigns)) > 0,
                "hsm_name": (
                    campaigns[-1]["whatsapp_template_name"]
                    if len(campaigns) > 0
                    else ""
                ),
            },
        }
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = _http_executor.submit(_http_post, data)
            response = future.result()
        else:
            response = _http_post(data)

        response = clean_response(response)

        if response.get("detail", {}).get("type") == "RuntimeError":
            raise Exception(
                f"Agent error: {response.get('detail',{}.get('message', 'Unknown error'))}"
            )

        # Resolve session_id: response > request > pre_session_id (generated at agent init) > run_id
        effective_session_id = (
            response.get("session_id") or session_id or pre_session_id or run_id
        )

        _camps = ", ".join(
            c.get("campaign_name", c.get("id", "?")) for c in (campaigns or [])
        )
        logger.info(
            f"[{user_id}] [{effective_session_id}]\n"
            f"  -> QA : {message}\n"
            f"  <- BOT: {response.get('text', '(empty)')}"
            + (
                f"\n  files={len(attachments)} images={len(images)}"
                if attachments or images
                else ""
            )
            + (f"\n  campaigns: {_camps}" if _camps else "")
        )
        save_interaction(
            message=message,
            answer=response,
            session_id=effective_session_id,
            user_id=user_id,
            files=attachments,
            images=images,
            run_id=run_id,
            scenario_group_id=scenario_group_id,
            scenario=scenario,
            campaigns=campaigns,
        )
        return response
    except Exception as e:
        logger.error(f"Error sending message to agent: {e}")
        return {
            "error": str(e),
            "abort": True,
        }


def save_interaction(
    message: str,
    answer: dict,
    user_id: str = "default_user",
    session_id: str = "",
    files: list = None,
    images: list = None,
    run_id: str = "",
    scenario_group_id: str = "",
    scenario: str = "",
    campaigns: list = None,
):
    """
    Save the interaction between the user and the agent to the database.
    session_id must be pre-resolved by the caller (never extracted here from answer).
    """
    try:
        log_db = LogDB()
        log_db.add(
            user_id=user_id,
            message=message,
            raw_response=json.dumps(answer),
            response=answer.get("text", ""),
            session_id=session_id,
            files=files or [],
            images=images or [],
            run_id=run_id,
            scenario_group_id=scenario_group_id,
            scenario=scenario,
            campaigns=campaigns,
        )
    except Exception as e:
        logger.error(f"Error saving interaction: {e}")


def save_analysis(
    analysis: str, session_id: str, run_id: str, complete: bool = False, *args, **kwargs
) -> Dict[str, str]:
    """
    Save the analysis generated by the AnalysisAgent to the database.
    Args:
        analysis (str): The insights text or JSON string to be saved.
        session_id (str): The ID of the session associated with the analysis.
        run_id (str): The run ID to associate with the analysis.
        complete (bool): Whether the conversation reached its objective.
    Returns:
        dict: A dictionary indicating the status of the save operation.
    """

    # If analysis is JSON, extract insights and complete from it (complete param takes precedence if explicitly set)
    analysis_dict = {}
    if isinstance(analysis, str):
        try:
            analysis_dict = json.loads(analysis)
        except json.JSONDecodeError:
            extracted = extract_json_blocks(analysis)
            if extracted and ("insights" in extracted or "complete" in extracted):
                analysis_dict = extracted
            else:
                analysis_dict = {"insights": analysis}
    elif isinstance(analysis, dict):
        analysis_dict = analysis
    else:
        logger.error("Invalid analysis format. Must be a JSON string or a dictionary.")
        return {
            "status": "error",
            "message": "Invalid analysis format. Must be a JSON string or a dictionary.",
        }

    # `complete` param wins if caller passed it explicitly; otherwise fall back to JSON field
    if complete:
        pass  # use the explicit value
    elif "complete" in analysis_dict:
        complete_val = analysis_dict["complete"]
        complete = (
            complete_val
            if isinstance(complete_val, bool)
            else str(complete_val).lower() == "true"
        )

    insights_text = analysis_dict.get("insights", "")
    logger.info(
        f"[analysis] session={session_id} complete={complete}\n"
        f"  {insights_text[:200]}{'...' if len(insights_text) > 200 else ''}"
    )
    try:
        log_db = LogDB()
        log_db.add_insight(
            session_id=session_id,
            run_id=run_id,
            analysis=insights_text,
            complete=complete,
        )
        logger.info(f"[analysis] saved ok")
        return {"status": "success", "message": "Analysis saved successfully."}
    except Exception as e:
        logger.error(f"Error saving analysis: {e}")
        return {"status": "error", "message": f"Error saving analysis: {e}"}
