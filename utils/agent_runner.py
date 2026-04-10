from loguru import logger
import os
from google.adk.sessions import InMemorySessionService
from datetime import datetime
from google.genai import types
from google.adk.runners import Runner


APP_NAME = os.getenv("APP_NAME", "default_app_name")


class Agent:
    def __init__(self, user_id: str, agent, session_service=None):
        self.user_id = user_id
        self.id = self._day_session_str(user_id)
        self.agent = agent
        self.runner: Runner | None = None
        self.session_service = session_service or InMemorySessionService()

    async def generate(self):
        """
        Generate an agent based on the provided agent name.
        """
        if not self.agent:
            raise ValueError("Agent name cannot be empty.")
        await self._init_runner()
        return self

    async def from_text(self, text: str):
        """
        Send a user message to the agent and handle streamed responses.
        Supports both text and function calls. Waits for the final response
        even if intermediate events (tool calls/responses) have no text.
        """
        message_content = types.Content(
            parts=[types.Part.from_text(text=text)],
            role="user",
        )
        collected_text = ""
        final_response_seen = False

        try:
            # pyrefly: ignore [missing-attribute]
            events = self.runner.run_async(
                user_id=self.user_id,
                new_message=message_content,
                session_id=self.session.id,
            )

            async for event in events:
                logger.debug(
                    f"Event received: author={getattr(event, 'author', None)}, "
                    f"final={event.is_final_response()}, "
                    f"has_content={bool(event.content)}"
                )

                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.function_call:
                            logger.info(
                                f"Function call: {part.function_call.name} "
                                f"args={part.function_call.args}"
                            )
                            continue
                        if part.function_response:
                            logger.info(
                                f"Function response: {part.function_response.name}"
                            )
                            continue
                        if part.text:
                            logger.debug(f"Text part received: {part.text}")
                            collected_text += part.text

                if event.is_final_response():
                    logger.info("Final response received.")
                    final_response_seen = True
                    break

            if not final_response_seen:
                logger.warning("Stream ended without a final response event.")

            return collected_text.strip() if collected_text else None

        except Exception as e:
            logger.exception(f"Exception during agent run: {e}")
            return None

    async def _init_runner(self):
        """
        Initialize the agent runner.
        """
        if not self.agent:
            raise ValueError("Agent not generated. Call generate() first.")
        self.session = await self.__get_session()
        self.runner = Runner(
            agent=self.agent,
            app_name=APP_NAME,
            session_service=self.session_service,
        )

    async def __get_session(self):
        logger.info(f"Getting session for user {self.user_id} and session {self.id}")
        try:
            session = await self.session_service.get_session(
                app_name=APP_NAME,
                user_id=self.user_id,
                session_id=self.id,
            )
            if session:
                return session
        except Exception as e:
            logger.error(f"Error getting session: {e}")
        return await self.session_service.create_session(
            app_name=APP_NAME,
            user_id=self.user_id,
            session_id=self.id,
        )

    def _day_session_str(self, user_id: str):
        """
        Get the session for the user.
        """
        return f"{user_id}_{datetime.now().strftime('%Y-%m-%d')}"
