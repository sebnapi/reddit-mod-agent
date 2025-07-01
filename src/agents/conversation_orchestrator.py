from typing import Dict, Any, Optional, List
from agents.conversation_state import ConversationState, Intent, ConversationMode
from agents.conversation_agents import (
    IntentClassificationAgent, ConversationAgent, ModerationActionAgent,
    QueryResponseAgent
)
from agents.override_rules_extraction import OverrideRuleExtractor
from agents.context_understanding import ContextUnderstandingAgent
from agents.base_agent import EventBus, ToolCall
import time


class ConversationOrchestrator:
    def __init__(self, meta_agent, post_agent, event_bus: Optional[EventBus] = None):
        self.meta_agent = meta_agent
        self.post_agent = post_agent
        self.event_bus = event_bus or EventBus()

        self.conversation_state = ConversationState()

        self.intent_classifier = IntentClassificationAgent()
        self.conversation_agent = ConversationAgent()
        self.moderation_agent = ModerationActionAgent()
        self.query_agent = QueryResponseAgent()
        self.context_understanding_agent = ContextUnderstandingAgent()
        self.override_rule_extractor = OverrideRuleExtractor(event_bus=event_bus)

        self.setup_event_handlers()

    def setup_event_handlers(self):
        self.event_bus.subscribe("post_selected", self._handle_post_selection)
        self.event_bus.subscribe("post_deselected", self._handle_post_deselection)

    def _handle_post_selection(self, data: Dict[str, Any]):
        post_id = data.get("post_id")
        if post_id:
            self.conversation_state.update_selected_entity("post", post_id)

            # Get the full post details from meta_agent
            selected_post = self.meta_agent.get_selected_post()
            if selected_post:
                self.conversation_state.update_selected_post_details(selected_post)

    def _handle_post_deselection(self, data: Dict[str, Any]):
        # Save any current override rules to the post before deselecting
        post_id = data.get("post_id")
        current_override_rules = self.conversation_state.get_post_override_rules()

        # Update the post in meta_agent storage with current override rules
        if post_id and current_override_rules:
            with self.meta_agent._lock:
                if post_id in self.meta_agent.todo_posts:
                    self.meta_agent.todo_posts[post_id]["override_rules"] = current_override_rules
                elif post_id in self.meta_agent.approved_posts:
                    self.meta_agent.approved_posts[post_id]["override_rules"] = current_override_rules

        self.conversation_state.update_selected_entity("post", None)
        self.conversation_state.update_selected_post_details(None)

    def process_message(self, user_message: str, data_loader) -> Dict[str, Any]:
        if not user_message.strip():
            return {"message": "Please provide a message.", "type": "error"}

        try:
            intent = self.intent_classifier.classify_intent(user_message, self.conversation_state)

            response = self._route_to_agent(user_message, intent, data_loader)

            actions_taken = response.get("actions_taken", [])
            agent_response = response.get("message", "")

            self.conversation_state.add_turn(user_message, intent, agent_response, actions_taken)

            self.event_bus.publish("conversation_turn", {
                "user_message": user_message,
                "intent": intent,
                "response": response
            })

            return response

        except Exception as e:
            error_response = {"message": f"Error processing message: {str(e)}", "type": "error"}

            fallback_intent = Intent(primary="CONVERSATION", confidence=0.1)
            self.conversation_state.add_turn(user_message, fallback_intent, error_response["message"])

            return error_response

    def _route_to_agent(self, message: str, intent: Intent, data_loader) -> Dict[str, Any]:
        if intent.primary == "MODERATION_ACTION":
            return self._handle_moderation_action(message, intent, data_loader)
        elif intent.primary == "MODERATION_QUERY":
            return self._handle_moderation_query(message, intent, data_loader)
        elif intent.primary == "SYSTEM_COMMAND":
            return self._handle_system_command(message, intent, data_loader)
        elif intent.primary == "FEEDBACK":
            return self._handle_feedback(message, intent, data_loader)
        else:
            return self._handle_conversation(message, intent, data_loader)

    def _handle_moderation_action(self, message: str, intent: Intent, data_loader) -> Dict[str, Any]:
        selected_post_id = self.conversation_state.selected_entities.get("post")

        if not selected_post_id:
            return {
                "message": "Please select a post first before taking moderation actions.",
                "type": "error"
            }

        if intent.secondary == "APPROVE_POST":
            return self._execute_approve(selected_post_id, message)
        elif intent.secondary == "REJECT_POST":
            return self._execute_reject(selected_post_id, message)
        elif intent.secondary == "FLAG_POST":
            return self._execute_flag(selected_post_id, message)
        else:
            action_result = self.moderation_agent.process_conversation(message, intent, self.conversation_state)

            if "error" in action_result:
                return {"message": "Could not understand the moderation action. Please be more specific.", "type": "error"}

            action = action_result.get("action")
            if action == "approve":
                return self._execute_approve(selected_post_id, action_result.get("reason", message))
            elif action == "reject":
                return self._execute_reject(selected_post_id, action_result.get("reason", message))
            elif action == "flag":
                return self._execute_flag(selected_post_id, action_result.get("reason", message))

            return {"message": action_result.get("message", "Action processed"), "type": "moderation_action"}

    def _handle_moderation_query(self, message: str, intent: Intent, data_loader) -> Dict[str, Any]:
        if intent.secondary == "QUERY_POST_STATUS":
            return self._query_post_status(message, intent)
        elif intent.secondary == "EXPLAIN_DECISION":
            return self._explain_decision(message, intent)
        elif intent.secondary == "SUMMARIZE_POST":
            return self._summarize_post(message, intent)
        else:
            query_result = self.query_agent.process_conversation(message, intent, self.conversation_state)

            if "error" in query_result:
                return {"message": "I couldn't process your query. Could you rephrase it?", "type": "error"}

            return {
                "message": query_result.get("response", "Query processed"),
                "type": "query_response",
                "data_provided": query_result.get("data_provided", [])
            }

    def _handle_system_command(self, message: str, intent: Intent, data_loader) -> Dict[str, Any]:
        try:
            # Get post context and existing override rules for this post
            post_context = self.conversation_state.selected_post_details
            existing_override_rules = self.conversation_state.get_post_override_rules()

            # Get rules from data loader for context
            data = data_loader.get_formatted_data()
            rules = data.get("rules", [])

            override_rule = self.override_rule_extractor.extract(
                message, post_context, rules, existing_override_rules
            )

            # Add new rule to the current post if extracted
            if override_rule:
                self.conversation_state.add_post_override_rule(override_rule)

            override_rules = self.conversation_state.get_post_override_rules()
            result = self.meta_agent._auto_review_posts(data_loader, override_rules)
            # Ensure we preserve the system_command type even if the underlying operation succeeds
            if not result.get("type"):
                result["type"] = "system_command"
            return result
        except Exception as e:
            # Handle data loading or processing errors gracefully
            return {
                "message": f"Auto-review failed: {str(e)}",
                "type": "system_command",
                "error_details": str(e),
                "approved_posts": [],
                "flagged_posts": []
            }

    def _handle_feedback(self, message: str, intent: Intent, data_loader) -> Dict[str, Any]:
        selected_post_id = self.conversation_state.selected_entities.get("post")

        if selected_post_id and (intent.requires_review or intent.has_new_override_rules):
            # Get post context and existing override rules for this post
            post_context = self.conversation_state.selected_post_details
            existing_override_rules = self.conversation_state.get_post_override_rules()

            # Get rules from data loader for context
            data = data_loader.get_formatted_data()
            rules = data.get("rules", [])

            override_rule = self.override_rule_extractor.extract(
                message, post_context, rules, existing_override_rules
            )

            # Add new rule to the current post if extracted
            if override_rule:
                self.conversation_state.add_post_override_rule(override_rule)

            override_rules = self.conversation_state.get_post_override_rules()
            return self._re_review_with_feedback(selected_post_id, message, override_rules, data_loader)

        return {"message": "Thank you for your feedback. I'll take it into account.", "type": "feedback"}

    def _handle_conversation(self, message: str, intent: Intent, data_loader) -> Dict[str, Any]:
        selected_post_id = self.conversation_state.selected_entities.get("post")

        if selected_post_id and intent.has_new_override_rules:
            # Get post context and existing override rules for this post
            post_context = self.conversation_state.selected_post_details
            existing_override_rules = self.conversation_state.get_post_override_rules()

            # Get rules from data loader for context
            data = data_loader.get_formatted_data()
            rules = data.get("rules", [])

            override_rule = self.override_rule_extractor.extract(
                message, post_context, rules, existing_override_rules
            )

            # Add new rule to the current post if extracted
            if override_rule:
                self.conversation_state.add_post_override_rule(override_rule)

            override_rules = self.conversation_state.get_post_override_rules()
            return self._re_review_with_feedback(selected_post_id, message, override_rules, data_loader)

        conversation_result = self.conversation_agent.process_conversation(message, intent, self.conversation_state)

        if "error" in conversation_result:
            return {"message": "I'm having trouble understanding. Could you rephrase?", "type": "conversation"}

        return {
            "message": conversation_result.get("response", "I understand."),
            "type": "conversation"
        }

    def _execute_approve(self, post_id: str, reason: str) -> Dict[str, Any]:
        try:
            result = self.meta_agent._approve_post(post_id, reason)
            return {
                "message": result.get("message", f"Post {post_id} approved successfully"),
                "type": "moderation_action",
                "action": "approve",
                "post_id": post_id,
                "actions_taken": ["approve_post"],
                "tool_result": result.get("tool_result")
            }
        except Exception as e:
            return {"message": f"Error approving post: {str(e)}", "type": "error"}

    def _execute_reject(self, post_id: str, reason: str) -> Dict[str, Any]:
        try:
            result = self.meta_agent._reject_post(post_id, reason)
            return {
                "message": result.get("message", f"Post {post_id} rejected successfully"),
                "type": "moderation_action",
                "action": "reject",
                "post_id": post_id,
                "actions_taken": ["reject_post"],
                "tool_result": result.get("tool_result")
            }
        except Exception as e:
            return {"message": f"Error rejecting post: {str(e)}", "type": "error"}

    def _execute_flag(self, post_id: str, reason: str) -> Dict[str, Any]:
        tool_call = ToolCall("flag_for_review", {"post_id": post_id, "reason": reason})
        result = tool_call.execute()

        return {
            "message": result.get("message", f"Post {post_id} flagged for review"),
            "type": "moderation_action",
            "action": "flag",
            "post_id": post_id,
            "actions_taken": ["flag_post"],
            "tool_result": result
        }

    def _query_post_status(self, message: str, intent: Intent) -> Dict[str, Any]:
        selected_post_id = self.conversation_state.selected_entities.get("post")

        if selected_post_id:
            selected_post = self.meta_agent.get_selected_post()
            if selected_post:
                status = "flagged" if selected_post_id in self.meta_agent.todo_posts else "approved"

                # Build status message with confidence if available
                message_parts = [f"Post {selected_post_id} is currently {status}."]
                message_parts.append(f"Title: {selected_post.get('title', '')[:50]}...")

                # Add confidence information for flagged posts
                if status == "flagged" and selected_post.get("confidence") is not None:
                    confidence = selected_post["confidence"]
                    confidence_level = selected_post.get("confidence_level", "unknown")
                    message_parts.append(f"🎯 Confidence: {confidence:.3f} ({confidence_level.upper()})")

                    # Add interpretation
                    if confidence >= 0.8:
                        message_parts.append("💪 High confidence violation - Clear rule break")
                    elif confidence >= 0.6:
                        message_parts.append("🤔 Medium confidence violation - Likely rule break")
                    else:
                        message_parts.append("🤷 Low confidence violation - May need human review")

                return {
                    "message": " ".join(message_parts),
                    "type": "query_response",
                    "data_provided": ["post_status", "post_title", "confidence_info"]
                }

        summary = self.meta_agent.get_posts_summary()
        return {
            "message": f"System status: {summary['todo_count']} posts flagged, {summary['approved_count']} approved",
            "type": "query_response",
            "data_provided": ["system_status"]
        }

    def _explain_decision(self, message: str, intent: Intent) -> Dict[str, Any]:
        selected_post_id = self.conversation_state.selected_entities.get("post")

        if selected_post_id:
            selected_post = self.meta_agent.get_selected_post()
            if selected_post and selected_post.get("explanation"):
                explanation_parts = [f"Decision explanation for post {selected_post_id}:"]
                explanation_parts.append(selected_post['explanation'])

                # Add confidence information if available
                if selected_post.get("confidence") is not None:
                    confidence = selected_post["confidence"]
                    confidence_level = selected_post.get("confidence_level", "unknown")
                    explanation_parts.append(f"\n🎯 Confidence Score: {confidence:.3f} ({confidence_level.upper()})")

                    # Add confidence interpretation
                    if confidence >= 0.8:
                        explanation_parts.append("This is a high-confidence violation - the system is very certain about this rule break.")
                    elif confidence >= 0.6:
                        explanation_parts.append("This is a medium-confidence violation - the system believes this likely breaks the rule.")
                    else:
                        explanation_parts.append("This is a low-confidence violation - the system is uncertain and recommends human review.")

                return {
                    "message": " ".join(explanation_parts),
                    "type": "query_response",
                    "data_provided": ["decision_explanation", "confidence_analysis"]
                }

        return {"message": "No decision explanation available for the current context.", "type": "query_response"}

    def _summarize_post(self, message: str, intent: Intent) -> Dict[str, Any]:
        selected_post_details = self.conversation_state.selected_post_details

        if not selected_post_details:
            return {
                "message": "Please select a post first before asking for a summary.",
                "type": "error"
            }

        post_title = selected_post_details.get("title", "No title")
        post_body = selected_post_details.get("body", "No content")
        post_id = selected_post_details.get("id", "Unknown")

        summary = f"Summary of post {post_id}:\n\n"
        summary += f"Title: {post_title}\n\n"

        if post_body:
            # Provide a concise summary of the content
            if len(post_body) > 200:
                summary += f"Content: {post_body[:200]}...\n\n"
                summary += f"This post contains {len(post_body)} characters of content."
            else:
                summary += f"Content: {post_body}"
        else:
            summary += "No content available."

        # Add moderation info if available
        if selected_post_details.get("explanation"):
            summary += f"\n\nModeration Status: {selected_post_details['explanation']}"

            # Add confidence information to moderation status
            if selected_post_details.get("confidence") is not None:
                confidence = selected_post_details["confidence"]
                confidence_level = selected_post_details.get("confidence_level", "unknown")
                summary += f"\n🎯 Confidence: {confidence:.3f} ({confidence_level.upper()})"

                # Add confidence interpretation
                if confidence >= 0.8:
                    summary += "\n💪 High confidence - System is very certain about this violation"
                elif confidence >= 0.6:
                    summary += "\n🤔 Medium confidence - System believes this likely violates rules"
                else:
                    summary += "\n🤷 Low confidence - System is uncertain, human review recommended"

        return {
            "message": summary,
            "type": "query_response",
            "data_provided": ["post_summary", "post_content", "post_title", "moderation_confidence"]
        }

    def _re_review_with_feedback(self, post_id: str, feedback_message: str, override_rules: List[str], data_loader) -> Dict[str, Any]:
        contextual_instruction = self.meta_agent._create_contextual_message(feedback_message)
        return self.meta_agent._re_review_selected_post_with_context(contextual_instruction, override_rules, data_loader)

    def get_conversation_summary(self) -> Dict[str, Any]:
        return {
            "conversation_turns": len(self.conversation_state.conversation_history),
            "selected_post": self.conversation_state.selected_entities.get("post"),
            "conversation_mode": self.conversation_state.conversation_mode.value,
            "recent_intents": [turn.intent.primary for turn in self.conversation_state.get_recent_context(5)]
        }