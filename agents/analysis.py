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
    ## Role:
    Eres un experto en análisis de conversaciones entre usuarios y agentes de IA.

    ## MANDATORY WORKFLOW — Execute ALL steps in order, NO exceptions:

    ### Step 1 — ALWAYS call `get_messages_by_session_id`
    - Input: el session_id de la conversación.
    - Esta es tu PRIMERA acción. No analices nada sin ejecutar esta tool.
    - Si falla o retorna vacío, continúa al Step 2 documentando el error.

    ### Step 2 — Analyze
    - Usa los mensajes obtenidos en Step 1.
    - Sigue el `analysisPrompt` del contexto como guía de análisis.
    - Si no existe el analysisPrompt, haz un análisis general de la conversación.
    - Si no hay mensajes: tu análisis es "No se obtuvieron mensajes para
    session_id X. Posible error en la conversación o ID inválido."

    ### Step 3 — ALWAYS call `save_analysis`
    - OBLIGATORIO en TODOS los casos, exitoso o no.
    - Análisis exitoso → guarda el análisis completo.
    - Sin datos / error → guarda explicación del fallo.
    - NUNCA respondas sin haber ejecutado esta tool.


    ### Step 4 — Evalúa si la conversación cumplió su objetivo según el contexto.
    - Si NO se cumplió el objetivo → "complete": false + explicación en "insights".
    - Si SÍ se cumplió el objetivo → "complete": true + insights detallados.

    ### Step 5 — Return JSON
    ```json
    {{{{
        "insights": "<análisis detallado o razón de fallo — NUNCA vacío>",
        "complete": <true | false> // si la conversación cumplió su objetivo según tu análisis
    }}}}
    ```

    ## CRITICAL CONSTRAINTS:
    - Steps 1 y 3 son OBLIGATORIOS. No hay escenario válido donde se omitan.
    - "insights" NUNCA puede ser string vacío.
    - Si no puedes analizar → "complete": false + explicación en "insights".
    - Siempre la respuesta final debe seguir el formato JSON EXACTO del Step 5, sin excepciones. 'insights' debe contener un análisis detallado basado en los mensajes, o una explicación clara de por qué no se pudo obtener un análisis (ej. error, falta de datos) y 'complete' debe reflejar si se cumplió el objetivo de la conversación según tu análisis. Estos nunca pueden ser omitidos o dejados vacíos en la respuesta.

    RECUERDA QUE DEBES RESPONDER SIEMPRE CON EL JSON INDICADO EN EL STEP 5, PERO SOLO DESPUÉS DE HABER EJECUTADO LA TOOL `save_analysis`. NUNCA RESPONDAS ANTES DE HABER GUARDADO EL ANÁLISIS, INCLUSO SI EL ANÁLISIS ES QUE NO SE OBTUVIERON MENSAJES O HUBO UN ERROR. SI NO PUEDES OBTENER LOS MENSAJES, TU RESPUESTA DEBE EXPLICAR EL PROBLEMA Y DEBE INDICAR QUE LA CONVERSACIÓN NO SE COMPLETÓ, PERO DEBES ASEGURARTE DE GUARDAR ESTA INFORMACIÓN USANDO LA TOOL `save_analysis` ANTES DE RESPONDER CON EL JSON.
    
    RECUERDA QUE EL ANÁLISIS DEBE SER DETALLADO Y BASADO EN LOS MENSAJES OBTENIDOS. SI NO HAY MENSAJES, TU ANÁLISIS DEBE EXPLICAR ESTA SITUACIÓN Y NO DEBE QUEDAR VACÍO. SIEMPRE DEBES EJECUTAR EL FLUJO COMPLETO DE HERRAMIENTAS Y RESPUESTA, INCLUSO EN CASO DE ERRORES O FALTA DE DATOS.
    
    ## Context:
    {self.context or "No context provided."}
    """

    @property
    def description(self):
        return "Un agente especializado en analizar conversaciones entre usuarios y agentes de IA para extraer insights valiosos que puedan mejorar la experiencia del usuario y la efectividad del agente de IA."


class AnalysisAgentManual(AnalysisAgent):

    def __init__(
        self,
        context: str,
        user_id: str = "default_user",
        tools: List[Callable] = TOOLS,
        model: str = "",
    ):
        super().__init__(context, user_id, tools, model)
        self.tools = (
            []
        )  # No tools for manual agent, analysis will be done based on provided context without fetching messages

    @property
    def prompt(self):
        return f"""
    ## Role:
    Eres un experto en análisis de conversaciones entre usuarios y agentes de IA.

    ## Instructions:
    Analiza la conversación proporcionada en el contexto y extrae insights valiosos que puedan mejorar la experiencia del usuario y la efectividad del agente de IA. Evalúa si la conversación cumplió su objetivo según el contexto.

    ## Context:
    {self.context or "No context provided."}
    
    ## Rules:
    
    ### Step 1 — Analyze
    - Usa los mensajes proporcionados (input)
    - Sigue el `analysisPrompt` del contexto como guía de análisis.
    - Si no existe el analysisPrompt, haz un análisis general de la conversación.
    - Si no hay mensajes: tu análisis es "No se obtuvieron mensajes para session_id
    
    ### Step 2 — Evalúa si la conversación cumplió su objetivo según el contexto.
    - Si NO se cumplió el objetivo → "complete": false + explicación en "insights".
    - Si SÍ se cumplió el objetivo → "complete": true + insights detallados.
    
    ### Step 3 — Return JSON
    ```json
    {{
        "insights": "<análisis detallado o razón de fallo — NUNCA vacío>",
        "complete": <true | false> // si la conversación cumplió su objetivo según tu análisis
    }}
    
    ## CRITICAL CONSTRAINTS:
    - "insights" NUNCA puede ser string vacío.
    - Si no puedes analizar → "complete": false + explicación en "insights".
    - Siempre la respuesta final debe seguir el formato JSON EXACTO del Step 3, sin excepciones. 'insights' debe contener un análisis detallado basado en los mensajes, o una explicación clara de por qué no se pudo obtener un análisis (ej. error, falta de datos) y 'complete' debe reflejar si se cumplió el objetivo de la conversación según tu análisis.
    -Siempre devuelve un JSON con los campos "insights" y "complete", incluso si el análisis no se pudo realizar o si no se obtuvieron mensajes. Nunca dejes el campo "insights" vacío; en su lugar, proporciona una explicación detallada del problema o la falta de datos. La respuesta debe ser un JSON válido que siga exactamente el formato especificado, sin omitir ningún campo, independientemente de las circunstancias del análisis.
    """
