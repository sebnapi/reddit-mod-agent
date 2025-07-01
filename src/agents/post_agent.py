import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from dotenv import load_dotenv
from openai import OpenAI
from data import DataLoader
from agents.base_agent import BaseAgent
from agents.confidence_rule_agent import ConfidenceRuleAgent

load_dotenv()

POST_SYSTEM_PROMPT = """
You are a Reddit Post Review Agent.
You will be given post data including the post content and subreddit rules.

Analyze the post against the applicable rules to determine if there are any violations.
IMPORTANT: Pay attention to any override_rules provided. These take ABSOLUTE PRECEDENCE over regular subreddit rules. Do not make exceptions, the moderator had something on his mind adding the rule.

Respond with ONLY a JSON object containing:
- "violation": boolean indicating if any rules were violated
- "rule_id": string ID of the violated rule (null if no violation, use override rule ID if applicable)
- "explanation": string explaining the violation or why no violation was found (only mention override rules if they were actually applied)

Be concise and decisive in your analysis. Do not mention override rules unless they were actually used in your decision.
"""

COMMENT_SYSTEM_PROMPT = """
You are a Reddit Comment Review Agent.
You will be given a comment along with the original post content and subreddit rules for context.

Analyze the comment against the applicable rules to determine if there are any violations.
IMPORTANT: Pay attention to any override_rules provided. These take ABSOLUTE PRECEDENCE over regular subreddit rules. Do not make exceptions, the moderator had something on his mind adding the rule.

Respond with ONLY a JSON object containing:
- "violation": boolean indicating if any rules were violated
- "rule_id": string ID of the violated rule (null if no violation, use override rule ID if applicable)
- "explanation": string explaining the violation or why no violation was found (only mention override rules if they were actually applied)

Be concise and decisive in your analysis. Do not mention override rules unless they were actually used in your decision.
"""

class MCPEnvelope:
    def __init__(self, post, subreddit, rules, review_target="post", target_comment=None, comments=None, override_rules=None):
        self.data = {
            "task": f"{review_target.title()} Review",
            "review_target": review_target,
            "post": {
                "title": post.get("title", ""),
                "body": post.get("body", ""),
                "id": post.get("id", "")
            },
            "subreddit": subreddit,
            "rules": rules
        }

        if override_rules:
            self.data["override_rules"] = []
            for rule in override_rules:
                self.add_override_rule(rule)

        if review_target == "comment" and target_comment:
            self.data["target_comment"] = {
                "body": target_comment.get("body", ""),
                "id": target_comment.get("id", ""),
                "author": target_comment.get("author", "")
            }
            self.data["comments"] = comments or []

    def add_override_rule(self, override_rule):
        if "override_rules" not in self.data:
            self.data["override_rules"] = []

        # Handle string override rules
        if isinstance(override_rule, str):
            override_rule_counter = len(self.data["override_rules"])
            formatted_override = {
                "id": f"override_rule_{override_rule_counter+1}",
                "rule_content": override_rule,
            }
            self.data["override_rules"].append(formatted_override)

    def add_override_rules(self, override_rules):
        """Add multiple override rules at once"""
        if isinstance(override_rules, list):
            for rule in override_rules:
                self.add_override_rule(rule)

    def to_json(self, indent=2):
        return json.dumps(self.data, indent=indent)

    def to_dict(self):
        return self.data

class BaseReviewAgent(BaseAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0, max_tokens=500):
        super().__init__(model, temperature, max_tokens)
        self.confidence_agent = ConfidenceRuleAgent()

    @abstractmethod
    def get_analysis_type(self) -> str:
        pass

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(data, MCPEnvelope):
            return self.review(data)
        else:
            return self._handle_error(ValueError("Expected MCPEnvelope data"))

    def _parse_response(self, content: str) -> dict:
        try:
            parsed = json.loads(content)
            if "violation" in parsed and "explanation" in parsed:
                return parsed
            else:
                return {
                    "violation": parsed.get("violation", False),
                    "rule_id": parsed.get("rule_id", None),
                    "explanation": parsed.get("explanation", "Analysis completed"),
                    **parsed
                }
        except json.JSONDecodeError:
            return {
                "violation": False,
                "rule_id": None,
                "explanation": f"Invalid JSON response: {content}",
                "error": True
            }

    def _handle_error(self, error: Exception) -> dict:
        # print(f"Error: {error}")
        return {
            "violation": False,
            "rule_id": None,
            "explanation": f"Error: {str(error)}",
            "error": True
        }

    def _calculate_confidence_score(self, mcp_envelope: MCPEnvelope, rule_id: str) -> float:
        try:
            # Extract the target content based on review type
            if mcp_envelope.data.get("review_target") == "comment":
                target_content = mcp_envelope.data.get("target_comment", {}).get("body", "")
            else:
                # For posts, combine title and body
                post_title = mcp_envelope.data.get("post", {}).get("title", "")
                post_body = mcp_envelope.data.get("post", {}).get("body", "")
                target_content = f"{post_title}\n\n{post_body}".strip()

            # Find the specific rule that was violated
            rule_text = self._get_rule_text(mcp_envelope.data.get("rules", []), rule_id)

            # If we can't find the rule, check override rules
            if not rule_text:
                override_rules = mcp_envelope.data.get("override_rules", [])
                rule_text = self._get_override_rule_text(override_rules, rule_id)

            if not rule_text or not target_content:
                return 0.5  # Default confidence when we can't calculate properly

            # Use the confidence agent to calculate the score
            confidence_result = self.confidence_agent.process({
                'rule': rule_text,
                'target': target_content
            })

            if confidence_result.get('error'):
                return 0.5  # Default confidence on error

            return confidence_result.get('confidence', 0.5)

        except Exception as e:
            return 0.5  # Default confidence on any error

    def _get_rule_text(self, rules: List[Dict], rule_id: str) -> str:
        for rule in rules:
            if rule.get("id") == rule_id:
                # Combine description and other relevant fields
                rule_parts = []
                if rule.get("short_name"):
                    rule_parts.append(rule["short_name"])
                if rule.get("description"):
                    rule_parts.append(rule["description"])
                if rule.get("violation_reason"):
                    rule_parts.append(f"Violation reason: {rule['violation_reason']}")
                return " - ".join(rule_parts) if rule_parts else ""
        return ""

    def _get_override_rule_text(self, override_rules: List[Dict], rule_id: str) -> str:
        for rule in override_rules:
            if rule.get("id") == rule_id:
                return rule.get("rule_content", "")
        return ""

    def review(self, mcp_envelope: MCPEnvelope) -> dict:
        try:
            messages = [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": f"Analyze this {self.get_analysis_type()} data:\n\n{mcp_envelope.to_json()}"}
            ]
            result = self._make_api_call(messages)

            # Add confidence score if there's a violation
            if result.get("violation") and result.get("rule_id"):
                confidence_score = self._calculate_confidence_score(mcp_envelope, result["rule_id"])
                result["confidence"] = confidence_score

                # Add confidence interpretation
                if confidence_score >= 0.8:
                    result["confidence_level"] = "high"
                elif confidence_score >= 0.6:
                    result["confidence_level"] = "medium"
                else:
                    result["confidence_level"] = "low"

            return result

        except Exception as e:
            return self._handle_error(e)

class PostSpecificAgent(BaseReviewAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0, max_tokens=500):
        super().__init__(model, temperature, max_tokens)

    def get_system_prompt(self) -> str:
        return POST_SYSTEM_PROMPT

    def get_analysis_type(self) -> str:
        return "post"

class CommentSpecificAgent(BaseReviewAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0, max_tokens=500):
        super().__init__(model, temperature, max_tokens)

    def get_system_prompt(self) -> str:
        return COMMENT_SYSTEM_PROMPT

    def get_analysis_type(self) -> str:
        return "comment"

def main():
    loader = DataLoader(subreddit_name="Viol_AskHistorians", post_ids=["violation_rule_0_example_1"])
    data = loader.get_formatted_data()

    print(f"Subreddit: {data['subreddit_name']}")

    post_agent = PostSpecificAgent()
    post_mcp_envelope = MCPEnvelope(
        data['posts'][0],
        data['subreddit_name'],
        data['rules'],
        review_target="post"
    )

    print("MCP Envelope with Override Rules:")
    print(post_mcp_envelope.to_json())

    post_result = post_agent.review(post_mcp_envelope)

    print("Post Review Result:")
    print(json.dumps(post_result, indent=2))

if __name__ == "__main__":
    main()
