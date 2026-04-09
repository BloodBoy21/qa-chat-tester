from loguru import logger
from tools import common

_BUILT_IN = {
    "send_message": common.send_to_agent,
}


def call_built_in(name: str, kwargs: dict):
    """Lanza ValueError si la herramienta no existe."""
    try:
        logger.info("********* BUILT IN ********")
        logger.info(f"Tool: {name}, Kwargs: {kwargs}")
        logger.info("***************************")
        return _BUILT_IN[name](**kwargs)
    except KeyError as e:
        logger.info("********* BUILT IN ERROR ********")
        logger.info(f"Tool: {name}, Kwargs: {kwargs}")
        logger.info(f"Error: {e}")
        logger.info("*******************************")
        return {"success": False, "error": f"Unknown internal tool: {name}"}
