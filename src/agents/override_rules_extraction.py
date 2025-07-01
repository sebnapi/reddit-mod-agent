from openai import OpenAI
import json
from typing import Dict, Any, List, Optional
from agents.base_agent import BaseAgent, EventBus

OVERRIDE_RULE_EXTRACTION_SYSTEM_PROMPT = (
    "You are an Override Rule Extraction Agent for a Reddit Moderation system.\n"
    "Your task is to analyze user instructions and extract ONE EXPLICIT override rule.\n\n"
    "CRITICAL: Only extract an override rule when the user uses VERY EXPLICIT override language.\n\n"
    "EXPLICIT override phrases (extract these):\n"
    "- 'ignore rule X'\n"
    "- 'ignore the rule about X'\n"
    "- 'override rule X'\n"
    "- 'make an exception to rule X'\n"
    "- 'don't apply rule X to this type of content'\n"
    "- 'suspend rule X for educational posts'\n\n"
    "DO NOT extract override rules for:\n"
    "- General feedback: 'this looks fine', 'I think this is okay', 'seems good'\n"
    "- Questions: 'why was this flagged?', 'what rule does this violate?'\n"
    "- Vague requests: 'be more lenient', 'this seems harsh'\n"
    "- Approval statements: 'approve this', 'this should be allowed'\n\n"
    "RULE FORMAT: Create BRIEF, CONCISE override rules.\n"
    "Format: 'ignore rule_X for [specific condition]' where X is the rule ID.\n"
    "Keep descriptions under 10 words. Do NOT include full rule descriptions.\n\n"
    "DUPLICATE PREVENTION: Check existing override rules carefully.\n"
    "If an override rule already exists for the SAME rule ID (e.g., rule_1), return null.\n"
    "Only create new override rules for rule IDs that don't have existing overrides.\n\n"
    "RULE IDENTIFICATION: \n"
    "- 'ignore rule 1' or 'ignore rule_1' → rule_1\n"
    "- 'ignore rule about insults' or 'personal attacks' → rule_2 (not rule_1!)\n"
    "- 'ignore civility rule' or 'politeness' → rule_1\n"
    "- 'ignore spam rule' or 'repetitive content' → rule_4\n"
    "- 'ignore topic rule' or 'stay on topic' → rule_3\n\n"
    "CAREFULLY match keywords to rule descriptions. 'Insults' = Personal Attacks = rule_2.\n"
    "Available rules and existing override rules will be provided.\n"
    "Reference rules by their ID (rule_1, rule_2, etc.).\n\n"
    "If no EXPLICIT override language is found, return null.\n"
    "If override already exists for that rule ID, return null.\n\n"
    "Respond with JSON: {'override_rule': 'ignore rule_X for [condition]' or null}"
)

class OverrideRuleExtractionMCP:
    def __init__(self, user_instruction: str, post_context: Optional[Dict[str, Any]] = None,
                 rules: Optional[List[Dict[str, Any]]] = None,
                 existing_override_rules: Optional[List[str]] = None):
        self.user_instruction = user_instruction
        self.post_context = post_context or {}
        self.rules = rules or []
        self.existing_override_rules = existing_override_rules or []

    def _build_context(self) -> str:
        context_parts = []

        # Add minimal post information
        if self.post_context.get("title"):
            context_parts.append(f"Post: {self.post_context['title'][:100]}")

        if self.post_context.get("rule_id"):
            context_parts.append(f"Current violation: Rule {self.post_context['rule_id']}")

        # Add available rules with IDs clearly marked
        if self.rules:
            context_parts.append("\nAvailable rules:")
            for rule in self.rules:
                if isinstance(rule, dict):
                    rule_id = rule.get("id", "unknown")
                    rule_name = rule.get("name", rule.get("short_name", ""))
                    context_parts.append(f"- {rule_id}: {rule_name}")

        # Add existing override rules
        if self.existing_override_rules:
            context_parts.append("\nExisting override rules (DO NOT CREATE DUPLICATES):")
            for override in self.existing_override_rules:
                context_parts.append(f"- {override}")

        return "\n".join(context_parts) if context_parts else "No context available"

    def to_json(self) -> List[Dict[str, str]]:
        context_info = self._build_context()
        full_prompt = f"Context:\n{context_info}\n\nUser instruction: {self.user_instruction}"

        return [
            {"role": "system", "content": OVERRIDE_RULE_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt}
        ]

class OverrideRuleExtractor(BaseAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0, event_bus: Optional[EventBus] = None):
        super().__init__(model, temperature, max_tokens=400)
        self.event_bus = event_bus

    def get_system_prompt(self) -> str:
        return OVERRIDE_RULE_EXTRACTION_SYSTEM_PROMPT

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        user_instruction = data.get("user_instruction", "")
        if not user_instruction:
            return {"override_rule": None}

        mcp = OverrideRuleExtractionMCP(
            user_instruction=user_instruction,
            post_context=data.get("post_context"),
            rules=data.get("rules"),
            existing_override_rules=data.get("existing_override_rules")
        )

        messages = mcp.to_json()
        result = self._make_api_call(messages)
        return result

    def extract(self, user_instruction: str, post_context: Optional[Dict[str, Any]] = None,
                rules: Optional[List[Dict[str, Any]]] = None,
                existing_override_rules: Optional[List[str]] = None) -> Optional[str]:
        data = {
            "user_instruction": user_instruction,
            "post_context": post_context or {},
            "rules": rules or [],
            "existing_override_rules": existing_override_rules or []
        }

        result = self.process(data)

        if "override_rule" in result:
            extracted_rule = result["override_rule"]

            # Publish event when a rule is extracted
            if self.event_bus and extracted_rule:
                event_data = {
                    "rule": extracted_rule,
                    "user_instruction": user_instruction,
                    "post_context": post_context,
                    "rules": rules,
                    "existing_override_rules": existing_override_rules
                }
                self.event_bus.publish("rule_extracted", event_data)

            return extracted_rule
        return None