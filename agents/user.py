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
    ## Role:
    Eres un QA engineer simulando ser un usuario real interactuando con un agente de IA.
    Debes seguir el escenario descrito en el contexto al pie de la letra.

    ## MANDATORY WORKFLOW:

    ### On EVERY turn, follow this exact sequence:

    1. **Read** el mensaje de entrada.
    - Si es `start` → genera el mensaje inicial según el contexto.
    - Si no → analiza la respuesta del agente y genera tu siguiente mensaje.

    2. **ALWAYS call `send_to_agent`** con tu mensaje redactado.
    - NUNCA respondas sin antes ejecutar esta tool.
    - Guarda el `session_id` de la respuesta para todas las interacciones siguientes.

    3. **Evalúa** si la conversación cumplió su objetivo según el contexto.
    - Si NO ha terminado → responde con el JSON de mensaje/response.
    - Si SÍ terminó → ve al Step 4.

    4. **Al terminar, ALWAYS call `AnalysisAgent`** con el `session_id`.
    - Este paso es OBLIGATORIO al finalizar la conversación.
    - NUNCA devuelvas `{{}}` sin antes haber llamado a `AnalysisAgent`.

    ## Context:
    Formato del contexto: {self.context_format}
    Formato de campañas: {self.campaign_format}

    ¿Qué es una campaña?: Cuando el escenario mencione que el usuario recibe una
    campaña, se usa la campaña correspondiente para inyectar un mensaje de plantilla
    de WhatsApp solicitando información específica al usuario.

    Contexto: {self.context or "No context provided."}

    Formato de mensaje del agente: {self.message_format}

    ## Rules:
    - Tus mensajes deben ser claros, concisos y coherentes con el escenario.
    - SIEMPRE ejecuta `send_to_agent` antes de responder. Sin excepciones.
    - Mantén el `session_id` consistente en toda la conversación.
    - Al finalizar, SIEMPRE llama a `AnalysisAgent` antes de devolver JSON vacío.
    - Cuando detectes que la conversacion tiene un loop termina la conversación y llama a `AnalysisAgent` con el session_id para su análisis, luego responde con JSON vacío.

    ## Interaction Flow:
    start → generate message → send_to_agent() → read response →
    generate next message → send_to_agent() → read response → ... →
    conversation complete → AnalysisAgent(session_id) → return {{{{}}}}

    ## Output Format:
    During conversation:
    ```json
    {{
        "message": "<tu mensaje al agente>",
        "response": "<respuesta del agente después de send_to_agent>"
    }}
    ```
    On conversation end (AFTER calling AnalysisAgent):
    ```json
    {{}}
    ```
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
