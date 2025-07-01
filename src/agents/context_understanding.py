from typing import Dict, Any, List, Optional
from agents.base_agent import BaseAgent
from agents.conversation_state import ConversationState
import re


class ContextUnderstandingAgent(BaseAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0.2, max_tokens=400):
        super().__init__(model, temperature, max_tokens)
        self.agent_type = "context_understanding"

    def get_system_prompt(self) -> str:
        return (
            "You are a Context Understanding Agent for a Reddit moderation system.\n"
            "Extract entities, resolve references, and understand context from user messages.\n\n"
            "Extract:\n"
            "- Post IDs (pattern: alphanumeric strings, often with underscores)\n"
            "- Rule references (rule numbers, rule names, policy mentions)\n"
            "- Actions mentioned (approve, reject, flag, review)\n"
            "- Pronouns and references (this, that, it, the post, etc.)\n"
            "- Temporal references (previous, earlier, last, recent)\n\n"
            "Resolve references based on conversation context:\n"
            "- 'this post' = currently selected post\n"
            "- 'that decision' = last moderation decision\n"
            "- 'the previous case' = last discussed post\n\n"
            "Respond with JSON:\n"
            "{\n"
            "  'entities': {\n"
            "    'post_ids': ['list of post IDs'],\n"
            "    'rule_refs': ['list of rule references'],\n"
            "    'actions': ['list of actions mentioned'],\n"
            "    'temporal_refs': ['list of time references']\n"
            "  },\n"
            "  'resolved_references': {\n"
            "    'post_reference': 'resolved post ID or null',\n"
            "    'rule_reference': 'resolved rule or null',\n"
            "    'action_reference': 'resolved action or null'\n"
            "  },\n"
            "  'context_confidence': 0.0-1.0\n"
            "}"
        )

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        message = data.get("message", "")
        context_state = data.get("conversation_state")

        context_info = self._build_context_info(context_state) if context_state else ""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Message: {message}\n\nContext: {context_info}"}
        ]

        result = self._make_api_call(messages)
        return result

    def _build_context_info(self, state: ConversationState) -> str:
        context_parts = []

        if state.selected_entities.get("post"):
            context_parts.append(f"Selected post: {state.selected_entities['post']}")

        if state.conversation_history:
            recent_turns = state.get_recent_context(2)
            context_parts.append("Recent conversation:")
            for turn in recent_turns:
                context_parts.append(f"- User: {turn.user_message[:100]}...")
                context_parts.append(f"- Intent: {turn.intent.primary}")

        return "\n".join(context_parts) if context_parts else "No context available"