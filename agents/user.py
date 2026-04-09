from .agent_base import AgentBase
from google.adk.agents import LlmAgent
from google.genai import types
from typing import List, Dict, Any, Callable, Union
from tools.common import send_to_agent

TOOLS = [send_to_agent]


class UserAgent(AgentBase):

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
            name="UserAgent",
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
      Eres un agente encargado de mandar mensajes a un servicio manejado por un agente de IA, debes enviar mensajes claros y concisos de acuerdo al caso de uso y las variables declaradas en el apartado de contexto.
      
      Si el mensaje de entrada es vacio significa que ha iniciado la conversación, en ese caso debes enviar un mensaje inicial de acuerdo al contexto declarado
      
      ## Context:
      {self.context or "No context provided."}
      
      ## Instructions:
      De acuerdo a la información proporcionada en el contexto, redacta un mensaje claro y conciso para el agente de IA. Asegúrate de incluir toda la información relevante y de formular tu mensaje de manera que sea fácil y una vez lo tengas ejecuta la tool 'send_to_agent' para enviar el mensaje al agente de IA.
    
        ## Output Format:
        Como respuesta debes mandar esto
        ```json
        {{
            "message": "El mensaje redactado para el agente de IA",
            "response": "La respuesta del agente de IA despues de ejecutar la tool send_to_agent"
        }}
        ```

    """

    @property
    def description(self):
        return "Agente encargado de redactar mensajes claros y concisos para un agente de IA, utilizando la información proporcionada en el contexto y enviando los mensajes a través de la tool 'send_to_agent'."
