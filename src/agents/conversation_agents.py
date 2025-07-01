from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from agents.conversation_state import Intent, ConversationState
import json
import re


class BaseConversationAgent(BaseAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0.3, max_tokens=800):
        super().__init__(model, temperature, max_tokens)
        self.agent_type = "conversation"

    def process_conversation(self, message: str, intent: Intent, state: ConversationState) -> Dict[str, Any]:
        return self.process({
            "message": message,
            "intent": intent,
            "conversation_state": state
        })

    def _build_context_prompt(self, state: ConversationState) -> str:
        context_parts = []

        if state.selected_entities.get("post"):
            post_id = state.selected_entities["post"]
            context_parts.append(f"Selected post ID: {post_id}")

            # Add full post context if available
            if hasattr(state, 'selected_post_details') and state.selected_post_details:
                post_details = state.selected_post_details
                context_parts.append(f"Post title: {post_details.get('title', 'No title')}")
                context_parts.append(f"Post content: {post_details.get('body', 'No content')[:500]}{'...' if len(post_details.get('body', '')) > 500 else ''}")
                if post_details.get('explanation'):
                    context_parts.append(f"Moderation explanation: {post_details['explanation']}")

                # Add existing override rules for this post
                override_rules = state.get_post_override_rules()
                if override_rules:
                    context_parts.append(f"Existing override rules: {override_rules}")
        if state.conversation_history:
            recent_turns = state.get_recent_context(2)
            context_parts.append("Recent conversation:")
            for turn in recent_turns:
                context_parts.append(f"User: {turn.user_message}")
                context_parts.append(f"Assistant: {turn.agent_response}")

        return "\n".join(context_parts) if context_parts else "No previous context."


class IntentClassificationAgent(BaseConversationAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0.1, max_tokens=400):
        super().__init__(model, temperature, max_tokens)
        self.agent_type = "intent_classifier"

    def get_system_prompt(self) -> str:
        return (
            "You are an Intent Classification Agent for a Reddit moderation system.\n"
            "Analyze user messages and classify their intent for proper routing.\n\n"
            "PRIMARY INTENTS:\n"
            "- MODERATION_ACTION: User explicitly wants to approve, reject, or flag posts (e.g., 'approve this post', 'reject this')\n"
            "- MODERATION_QUERY: User asking about posts, rules, or status (including summarize, explain, describe post content)\n"
            "- CONVERSATION: General chat, clarification, context discussion\n"
            "- SYSTEM_COMMAND: Auto-review, configuration, system operations\n"
            "- FEEDBACK: User providing guidance, override rules, or instructions about how to handle content\n"
            "SECONDARY INTENTS (for MODERATION_ACTION):\n"
            "- APPROVE_POST, REJECT_POST, FLAG_POST\n\n"
            "SECONDARY INTENTS (for MODERATION_QUERY):\n"
            "- QUERY_POST_STATUS, QUERY_RULES, EXPLAIN_DECISION, SUMMARIZE_POST\n\n"
            "QUERY CLASSIFICATION GUIDELINES:\n"
            "- 'what's the issue', 'why flagged', 'explain decision', 'what's wrong' = EXPLAIN_DECISION\n"
            "- 'summarize post', 'what's this about', 'post content' = SUMMARIZE_POST\n"
            "- 'post status', 'is approved', 'what happened to post' = QUERY_POST_STATUS\n"
            "- 'what are rules', 'rule details', 'moderation guidelines' = QUERY_RULES\n\n"
            "CRITICAL DISTINCTION:\n"
            "- 'ignore this rule' = FEEDBACK (override instruction, not rejection)\n"
            "- 'be lenient' = FEEDBACK (guidance, not action)\n"
            "- 'overlook this violation' = FEEDBACK (override instruction)\n"
            "- 'approve this post' = MODERATION_ACTION (explicit action)\n"
            "- 'reject this post' = MODERATION_ACTION (explicit action)\n\n"
            "OVERRIDE RULES: Phrases like 'ignore', 'overlook', 'be lenient', 'allow this', 'make exception' indicate override rules.\n"
            "These should be FEEDBACK with has_override_rules=true and requires_review=true.\n"
            "IMPORTANT: Each 'ignore rule X' command should trigger has_override_rules=true, even if other override rules exist.\n"
            "Multiple different override rules can be created for different rule IDs.\n\n"
            "Extract entities: post_ids, rule_references, action_types\n"
            "Determine if re-review is needed or if new override rules are present.\n\n"
            "Respond with JSON: {\n"
            "  'primary_intent': 'string',\n"
            "  'secondary_intent': 'string or null',\n"
            "  'confidence': 0.0-1.0,\n"
            "  'entities': {'post_ids': [], 'rule_refs': [], 'actions': []},\n"
            "  'requires_review': boolean,\n"
            "  'has_override_rules': boolean,\n"
            "  'tools_needed': []\n"
            "}"
        )

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        message = data.get("message", "")
        context_state = data.get("conversation_state")

        context_prompt = ""
        if context_state:
            context_prompt = f"\n\nContext: {self._build_context_prompt(context_state)}"

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Message: {message}{context_prompt}"}
        ]

        result = self._make_api_call(messages)
        return result

    def classify_intent(self, message: str, state: ConversationState) -> Intent:
        result = self.process_conversation(message, None, state)

        if "error" in result:
            return Intent(primary="CONVERSATION", confidence=0.5)

        return Intent(
            primary=result.get("primary_intent", "CONVERSATION"),
            secondary=result.get("secondary_intent"),
            confidence=result.get("confidence", 0.5),
            entities=result.get("entities", {}),
            requires_review=result.get("requires_review", False),
            has_new_override_rules=result.get("has_override_rules", False),
            tool_calls_needed=result.get("tools_needed", [])
        )


class ConversationAgent(BaseConversationAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0.7, max_tokens=600):
        super().__init__(model, temperature, max_tokens)
        self.agent_type = "conversation"

    def get_system_prompt(self) -> str:
        return (
            "You are a Conversational Agent for a Reddit moderation system.\n"
            "Handle natural dialogue, provide explanations, and maintain context.\n\n"
            "Your role:\n"
            "- Engage in natural conversation about moderation topics\n"
            "- Provide clarifications and explanations\n"
            "- Help users understand the system and processes\n"
            "- Maintain conversation flow and context\n"
            "- Be helpful, professional, and informative\n\n"
            "Do NOT:\n"
            "- Execute moderation actions (approve/reject posts)\n"
            "- Make system changes\n"
            "- Override rules without proper intent\n\n"
            "Respond naturally and conversationally in plain text."
        )

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        message = data.get("message", "")
        intent = data.get("intent")
        state = data.get("conversation_state")

        context_prompt = self._build_context_prompt(state) if state else ""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Context: {context_prompt}\n\nUser message: {message}"}
        ]

        # For conversation agent, we want plain text response
        temp_format = self.response_format
        self.response_format = None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            content = response.choices[0].message.content.strip()
            return {"response": content, "type": "conversation"}
        except Exception as e:
            return {"response": f"I apologize, but I encountered an error: {str(e)}", "type": "conversation"}
        finally:
            self.response_format = temp_format


class ModerationActionAgent(BaseConversationAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0.2, max_tokens=500):
        super().__init__(model, temperature, max_tokens)
        self.agent_type = "moderation_action"

    def get_system_prompt(self) -> str:
        return (
            "You are a Moderation Action Agent for a Reddit moderation system.\n"
            "Handle requests to approve, reject, or flag posts.\n\n"
            "Your responsibilities:\n"
            "- Process moderation action requests\n"
            "- Validate action parameters\n"
            "- Provide clear feedback on actions taken\n"
            "- Ensure proper reasoning for actions\n\n"
            "Respond with JSON containing:\n"
            "{\n"
            "  'action': 'approve|reject|flag',\n"
            "  'post_id': 'string',\n"
            "  'reason': 'string',\n"
            "  'success': boolean,\n"
            "  'message': 'user-friendly message'\n"
            "}"
        )

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        message = data.get("message", "")
        intent = data.get("intent")
        state = data.get("conversation_state")

        context_prompt = self._build_context_prompt(state) if state else ""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Context: {context_prompt}\n\nAction request: {message}\nIntent: {intent.secondary if intent else 'unknown'}"}
        ]

        result = self._make_api_call(messages)
        return result


class QueryResponseAgent(BaseConversationAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0.3, max_tokens=600):
        super().__init__(model, temperature, max_tokens)
        self.agent_type = "query_response"

    def get_system_prompt(self) -> str:
        return (
            "You are a Query Response Agent for a Reddit moderation system.\n"
            "Answer questions about posts, rules, status, and moderation decisions.\n\n"
            "Your responsibilities:\n"
            "- Answer questions about post status and content\n"
            "- Summarize posts when requested\n"
            "- Explain moderation rules and decisions\n"
            "- Provide system status information\n"
            "- Help users understand moderation processes\n\n"
            "When you have access to post content, provide detailed summaries and analysis.\n"
            "If asked to summarize a post, provide a concise but comprehensive summary.\n\n"
            "Provide clear, informative responses. Use JSON format:\n"
            "{\n"
            "  'response': 'detailed answer',\n"
            "  'type': 'query_response',\n"
            "  'data_provided': ['list', 'of', 'info', 'types']\n"
            "}"
        )

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        message = data.get("message", "")
        intent = data.get("intent")
        state = data.get("conversation_state")

        context_prompt = self._build_context_prompt(state) if state else ""

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Context: {context_prompt}\n\nQuery: {message}"}
        ]

        result = self._make_api_call(messages)
        return result


