from .agent_base import AgentBase
from google.adk.agents import LlmAgent
from google.genai import types
from typing import Any, List, Callable
from tools.common import send_to_agent

TOOLS = [send_to_agent]


class UserAgent(AgentBase):

    def __init__(
        self,
        context: str,
        user_id: str = "default_user",
        tools: List[Callable] = TOOLS,
        model: str = "",
        sub_agents: List[Any] = [],
    ):
        super().__init__(context, user_id, tools, model, sub_agents)

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
      Eres un QA engineer simulando ser un usuario en diferentes escenarios (usar el escenario que se proporciona en el contexto)  encargado de mandar mensajes a un servicio manejado por un agente de IA, debes enviar mensajes claros y concisos de acuerdo al caso de uso y las variables declaradas en el apartado de contexto.
      
      Si el mensaje de entrada es 'start' significa que ha iniciado la conversación, en ese caso debes enviar un mensaje inicial de acuerdo al contexto declarado, si es diferente a 'start' entonces debes responder al mensaje anterior de la conversación, siempre tomando en cuenta el contexto declarado.
      
      Debes guardar 'session_id' de la respuesta para usarla en las siguientes interacciones, esto con el fin de mantener la conversación en el mismo contexto.

       Recuerda que eres el usuario en esta interracion y tus mensajes son presentados al agente de IA, por lo que debes redactar tus mensajes de manera clara y concisa para que el agente de IA pueda entenderlos y responder de manera adecuada.
      
      ## Context:
      Formato del contexto:
      {self.context_format}
      Formato de campañas disponibles:
      {self.campaign_format}
      Que es una campaña?: Cuando el escenario mencione que el usuario recibe una campaña se usará la campaña correspondiente en "Campañas" para inyectar a la conversación y simular la recepción de la campaña (mensaje de plantilla de WhatsApp solicitando información específica al usuario).
      Contexto de la conversación:
      {self.context or "No context provided."}
      
      ##Formato de mensaje recibido por el agente de IA:
        {self.message_format}
    
      ## Instructions:
      De acuerdo a la información proporcionada en el contexto, redacta un mensaje claro y conciso para el agente de IA. Asegúrate de incluir toda la información relevante y de formular tu mensaje de manera que sea fácil y una vez lo tengas ejecuta la tool 'send_to_agent' para enviar el mensaje al agente de IA.
    
      Termina la interacción devolviendo una respuesta vacia cuando consideres que la conversación ha cumplido su objetivo o que no hay más información relevante que proporcionar. Y llama al agente `AnalysisAgent` para que analice la conversación y entregue insights relevantes sobre el comportamiento del usuario, la efectividad del agente de IA y cualquier otro aspecto relevante que pueda ser útil para mejorar la experiencia del usuario y la performance del agente de IA.Este agente usa el sesion_id de la conversación para analizar los mensajes intercambiados entre el usuario y el agente de IA.
        ## Output Format:
        Como respuesta debes mandar esto
        ```json
        {{
            "message": "El mensaje redactado para el agente de IA",
            "response": "La respuesta del agente de IA despues de ejecutar la tool send_to_agent"
        }}
        ```
        Si debes terminar la conversación, devuelve:
        ```json
        {{}}
        ```
        SIEMPRE RESPONDE EN FORMATO JSON, NUNCA RESPONDAS EN TEXTO PLANO, SI NO HAY INFORMACIÓN RELEVANTE QUE PROPORCIONAR O CONSIDERAS QUE LA CONVERSACIÓN HA CUMPLIDO SU OBJETIVO DEVUELVE UNA RESPUESTA VACIA.

    """

    @property
    def description(self):
        return "Agente encargado de redactar mensajes claros y concisos para un agente de IA, utilizando la información proporcionada en el contexto y enviando los mensajes a través de la tool 'send_to_agent'."

    @property
    def message_format(self):
        return """
        AgentResponse {
        session_id: string           // UUID de la sesión
        text: string                 // Respuesta final del bot en texto plano
        images: string[]             // URLs de imágenes en la respuesta (puede estar vacío)
        messages: Message[]          // Lista de mensajes generados
        tool_calls: ToolCall[]       // Llamadas a herramientas ejecutadas (puede estar vacío)
        requires_confirmation: bool? // Si requiere confirmación del usuario (nullable)
        metadata: object             // Metadata adicional (puede estar vacío)
        traces: Trace[]              // Trazas de ejecución del agente
        }

        Message {
        author: string               // "bot" | "user"
        text: string                 // Contenido del mensaje
        images: string[]             // Imágenes adjuntas
        metadata: {
            agent: string              // Nombre del agente (e.g. "MultiAgent")
            model: string              // Modelo usado (e.g. "gemini/gemini-2.5-flash")
        }
        }

        Trace {
        created_at: string           // Timestamp ISO
        updated_at: string           // Timestamp ISO
        title: string                // "Agent before" | "Model before" | "Model after" | "Agent after"
        tool: bool                   // Si la traza es de una herramienta
        agent: string                // Nombre del agente
        type: string                 // "agent_input" | "model_input" | "model_output" | "agent_output"
        when: string                 // "before" | "after"
        is_response: bool            // Si es parte de la respuesta final
        payload: object              // Contenido variable según el type
        account_id: int              // ID de cuenta
        user_id: int                 // ID de usuario
        }

        UsageMetadata {                // Dentro de payload en traces tipo "model_output"
        candidatesTokenCount: int
        promptTokenCount: int
        thoughtsTokenCount: int
        totalTokenCount: int
        trafficType: string          // e.g. "ON_DEMAND"
        }
    """

    @property
    def context_format(self):
        return """
        {
        user_id: string        // ID del usuario que ejecuta la prueba
        objective: string      // Descripción del objetivo de la prueba
        scenario: string       // Contexto narrativo del escenario
        evidence: string       // URL del archivo de evidencia (imagen S3)
        ce: string             // Nombre del Centro Educativo
        prompt: string         // Instrucciones paso a paso en Markdown para ejecutar la prueba,
        analysisPrompt: string // Instrucciones para el análisis posterior de la conversación por parte del agente AnalysisAgent
        }
    """

    @property
    def campaign_format(self):
        return """
        {
        campaigns: [
            {
            campaign_id: string           // ID único de la campaña
            campaign_name: string         // Nombre descriptivo de la campaña
            whatsapp_template_name: string // Nombre del template de WhatsApp asociado
            }
        ]
        }
    """
