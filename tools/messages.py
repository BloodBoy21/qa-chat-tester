from loguru import logger
from db.sql import LogDB


def get_messages_by_session_id(
    session_id: str, run_id: str, *args, **kwargs
) -> list[dict]:
    """
    Get messages from the database by session ID.
    Args:
        session_id (str): The ID of the session to retrieve messages for.
        run_id (str): The run ID to filter messages.
    Returns:
        list: A list of messages associated with the given session ID.
    """
    log_db = LogDB()
    messages = log_db.get_by_session(session_id, run_id)
    messages = [
        {
            "message_sent": message["message"],
            "response_received": message["response"],
            "files": message.get("files", []),
            "images": message.get("images", []),
        }
        for message in messages
    ]
    logger.info(f"Retrieved {len(messages)} messages for session_id: {session_id}")
    return messages
