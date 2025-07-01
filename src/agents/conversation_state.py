from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field
import time


class ConversationMode(Enum):
    ASSISTANT = "assistant"

    CONFIRMATION = "confirmation"
    FEEDBACK = "feedback"


@dataclass
class Intent:
    primary: str
    secondary: Optional[str] = None
    confidence: float = 0.0
    entities: Dict[str, Any] = field(default_factory=dict)
    requires_review: bool = False
    has_new_override_rules: bool = False
    tool_calls_needed: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.entities is None:
            self.entities = {}
        if self.tool_calls_needed is None:
            self.tool_calls_needed = []


@dataclass
class ConversationTurn:
    timestamp: float
    user_message: str
    intent: Intent
    agent_response: str
    actions_taken: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.actions_taken is None:
            self.actions_taken = []


class ConversationState:
    def __init__(self):
        self.current_intent: Optional[Intent] = None
        self.conversation_history: List[ConversationTurn] = []
        self.pending_actions: List[Dict[str, Any]] = []
        self.user_preferences: Dict[str, Any] = {}

        self.selected_entities: Dict[str, Any] = {
            "post": None,
            "rule": None,
            "subreddit": None
        }
        self.selected_post_details: Optional[Dict[str, Any]] = None
        self.conversation_mode: ConversationMode = ConversationMode.ASSISTANT
        self.last_activity: float = time.time()
        self.session_context: Dict[str, Any] = {}

    def add_turn(self, user_message: str, intent: Intent, agent_response: str, actions: List[str] = None):
        turn = ConversationTurn(
            timestamp=time.time(),
            user_message=user_message,
            intent=intent,
            agent_response=agent_response,
            actions_taken=actions or []
        )
        self.conversation_history.append(turn)
        self.current_intent = intent
        self.last_activity = time.time()

    def get_recent_context(self, turns: int = 3) -> List[ConversationTurn]:
        return self.conversation_history[-turns:] if turns > 0 else self.conversation_history

    def update_selected_entity(self, entity_type: str, entity_value: Any):
        if entity_type in self.selected_entities:
            self.selected_entities[entity_type] = entity_value

    def update_selected_post_details(self, post_details: Optional[Dict[str, Any]]):
        self.selected_post_details = post_details

    def clear_pending_actions(self):
        self.pending_actions.clear()

    def add_pending_action(self, action: Dict[str, Any]):
        self.pending_actions.append(action)


        self.conversation_mode = ConversationMode.ASSISTANT

    def add_post_override_rule(self, rule: str):
        """Add an override rule to the currently selected post"""
        if self.selected_post_details and rule:
            if "override_rules" not in self.selected_post_details:
                self.selected_post_details["override_rules"] = []
            if rule not in self.selected_post_details["override_rules"]:
                self.selected_post_details["override_rules"].append(rule)

    def get_post_override_rules(self) -> List[str]:
        """Get override rules for the currently selected post"""
        if self.selected_post_details:
            return self.selected_post_details.get("override_rules", [])
        return []

    def clear_post_override_rules(self):
        """Clear override rules for the currently selected post"""
        if self.selected_post_details:
            self.selected_post_details.pop("override_rules", None)

    def is_stale(self, timeout_minutes: int = 30) -> bool:
        return (time.time() - self.last_activity) > (timeout_minutes * 60)