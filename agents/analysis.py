from .agent_base import AgentBase
from google.adk.agents import LlmAgent
from google.genai import types
from typing import List, Callable
from tools.messages import get_messages_by_session_id
from tools.common import save_analysis

TOOLS = [get_messages_by_session_id, save_analysis]


class AnalysisAgent(AgentBase):

    def __init__(
        self,
        context: str,
        user_id: str = "default_user",
        tools: List[Callable] = TOOLS,
        model: str = "",
    ):
        super().__init__(context, user_id, tools, model)

    def Build(self):
        return LlmAgent(
            name="AnalysisAgent",
            model=self.model,
            instruction=self.prompt,
            # pyrefly: ignore [missing-attribute]
            description=self.description,
            generate_content_config=types.GenerateContentConfig(
                max_output_tokens=1000,
                temperature=0.5,
                top_p=0.95,
                top_k=40,
            ),
            tools=[self._build_tool(tool) for tool in self.tools],
            sub_agents=self.sub_agents,
        )

    @property
    def prompt(self):
        return f"""
         ## Instruction:
         Eres un experto en análisis de conversaciones entre un usuario y un agente de IA, tu tarea es analizar la conversación y proporcionar insights relevantes sobre el comportamiento del usuario, la efectividad del agente de IA y cualquier otro aspecto relevante que pueda ser útil para mejorar la experiencia del usuario y la performance del agente de IA.
         
         Debes usar el contexto proporcionado para entender el escenario de la conversación y proporcionar insights específicos y accionables basados en ese contexto.
         
         El input proporcionado es el id de la conversacion a analizar, debes usar la tool 'get_messages_by_session_id' para obtener los mensajes de la conversación y basar tu análisis en esos mensajes.
         
         Una vez tengas el analisis llama a la tool `save_analysis` para guardar el analisis realizado, esta tool recibe un string con el analisis detallado realizado.
         ## Context:
         {self.context or "No context provided."}
         
         ## Output Format:
         Debes responder en formato JSON con la siguiente estructura:
         ```json
         {{
             "insights": "Un análisis detallado de la conversación, incluyendo patrones de comportamiento del usuario, efectividad del agente de IA, áreas de mejora y cualquier otro insight relevante basado en el contexto proporcionado.",
             }}
        ```
        Recuerda que siempre se debe ejecutar la tool `save_analysis` con el análisis realizado para guardar el resultado del análisis si es exitoso, si no se puede realizar el análisis se guarda con un mensaje indicando que no se pudo realizar el análisis.

    """

    @property
    def description(self):
        return "Un agente especializado en analizar conversaciones entre usuarios y agentes de IA para extraer insights valiosos que puedan mejorar la experiencia del usuario y la efectividad del agente de IA."
