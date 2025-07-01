import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import threading
import time
from typing import Dict, Any, List, Optional, Callable
from agents.base_agent import BaseAgent, EventBus, ToolCall
from agents.post_agent import MCPEnvelope
from agents.conversation_orchestrator import ConversationOrchestrator


class MetaChatAgent:
    def __init__(self, post_agent, override_rule_extractor, event_bus: Optional[EventBus] = None):
        self.post_agent = post_agent
        self.override_rule_extractor = override_rule_extractor
        self.event_bus = event_bus or EventBus()

        self.approved_posts: Dict[str, Dict[str, Any]] = {}
        self.todo_posts: Dict[str, Dict[str, Any]] = {}
        self.selected_post_id: Optional[str] = None
        self.selected_post_context: Optional[Dict[str, Any]] = None  # Full post context

        self.agent_registry: List[BaseAgent] = [post_agent]
        self.tool_call_history: List[ToolCall] = []

        self._lock = threading.Lock()

        self.conversation_orchestrator = ConversationOrchestrator(
            meta_agent=self,
            post_agent=post_agent,
            event_bus=self.event_bus
        )

        self.event_bus.subscribe("post_selected", self._handle_post_selection)
        self.event_bus.subscribe("background_posts_loaded", self._handle_background_posts)

    def add_agent(self, agent: BaseAgent):
        self.agent_registry.append(agent)

    def get_selected_post(self) -> Optional[Dict[str, Any]]:
        if self.selected_post_id:
            return self.todo_posts.get(self.selected_post_id) or self.approved_posts.get(self.selected_post_id)
        return None

    def select_post(self, post_id: str):
        with self._lock:
            if post_id == self.selected_post_id:
                self.selected_post_id = None
                self.selected_post_context = None
                self.event_bus.publish("post_deselected", {"post_id": post_id})
            else:
                self.selected_post_id = post_id
                # Store full post context for use in conversations
                selected_post = self.todo_posts.get(post_id) or self.approved_posts.get(post_id)
                if selected_post:
                    self.selected_post_context = {
                        "post_id": post_id,
                        "title": selected_post.get("title", ""),
                        "body": selected_post.get("body", ""),
                        "current_status": "flagged" if post_id in self.todo_posts else "approved",
                        "explanation": selected_post.get("explanation", ""),
                        "rule_id": selected_post.get("rule_id"),
                        "violation": selected_post.get("violation", False),
                        "override_rules": selected_post.get("override_rules", [])
                    }

                    # Add confidence information if available
                    if selected_post.get("confidence") is not None:
                        self.selected_post_context["confidence"] = selected_post.get("confidence")
                        self.selected_post_context["confidence_level"] = selected_post.get("confidence_level", "unknown")

                self.event_bus.publish("post_selected", {"post_id": post_id})

    def _handle_post_selection(self, data: Dict[str, Any]):
        post_id = data.get("post_id")
        if post_id:
            self.selected_post_id = post_id

    def _handle_background_posts(self, data: Dict[str, Any]):
        approved_posts = data.get("approved_posts", [])
        flagged_posts = data.get("flagged_posts", [])

        with self._lock:
            for post in approved_posts:
                self.approved_posts[post["id"]] = post
            for post in flagged_posts:
                self.todo_posts[post["id"]] = post

    def interact(self, user_instruction: str, data_loader) -> Dict[str, Any]:
        return self.conversation_orchestrator.process_message(user_instruction, data_loader)

    def _process_contextual_user_message(self, user_instruction: str, data_loader) -> Dict[str, Any]:
        """Process user message with context of selected post if available"""
        # Get existing override rules from conversation orchestrator if available
        override_rules = []

        if self.selected_post_context:
            # Add post context to the user instruction
            contextual_instruction = self._create_contextual_message(user_instruction)

            # Re-review the selected post with the new context
            return self._re_review_selected_post_with_context(contextual_instruction, override_rules, data_loader)
        else:
            # No post selected, do general auto review
            return self._auto_review_posts(data_loader, override_rules)

    def _create_contextual_message(self, user_instruction: str) -> str:
        """Create a contextual message that includes the selected post information"""
        if not self.selected_post_context:
            return user_instruction

        context = self.selected_post_context
        contextual_message = f"""
MODERATOR MESSAGE ABOUT SELECTED POST:
Post ID: {context['post_id']}
Title: {context['title']}
Content: {context['body'][:500]}{'...' if len(context['body']) > 500 else ''}
Current Status: {context['current_status']}
Previous Explanation: {context['explanation']}

MODERATOR INSTRUCTION: {user_instruction}

Please process this instruction specifically in the context of the above post.
"""
        return contextual_message

    def _re_review_selected_post_with_context(self, contextual_instruction: str, override_rules: List[str], data_loader) -> Dict[str, Any]:
        """Re-review selected post with full context and user message"""
        if not self.selected_post_context:
            return {"approved_posts": [], "flagged_posts": [], "message": "No post selected"}

        data = data_loader.get_formatted_data()

        target_post = {
            "id": self.selected_post_context["post_id"],
            "title": self.selected_post_context["title"],
            "body": self.selected_post_context["body"]
        }

        # Create MCP envelope with context
        mcp_envelope = MCPEnvelope(
            post=target_post,
            subreddit=data["subreddit_name"],
            rules=data["rules"],
            review_target="post"
        )

        # Add override rules if any
        if override_rules:
            mcp_envelope.add_override_rules(override_rules)

        analysis_result = self.post_agent.review(mcp_envelope)
        post_info = self._create_post_info(target_post, analysis_result)

        # Update post status and execute appropriate tool based on new analysis
        actions_taken = []
        tool_result = None

        with self._lock:
            if analysis_result.get("violation"):
                self.todo_posts[post_info["id"]] = post_info
                self.approved_posts.pop(post_info["id"], None)
                self.selected_post_context["current_status"] = "flagged"
                message = f"Re-reviewed post {self.selected_post_id}: Still flagged - {analysis_result.get('explanation', 'Analysis completed')}"
            else:
                self.approved_posts[post_info["id"]] = post_info
                self.todo_posts.pop(post_info["id"], None)
                self.selected_post_context["current_status"] = "approved"

                # Execute approve_post tool since re-review shows no violation
                tool_call = ToolCall("approve_post", {
                    "post_id": self.selected_post_id,
                    "reason": f"Re-reviewed with override rules: {analysis_result.get('explanation', 'No violations found')}"
                })
                tool_result = tool_call.execute()
                self.tool_call_history.append(tool_call)
                actions_taken.append("approve_post")

                # Clear selection after approval
                self.selected_post_id = None
                self.selected_post_context = None

                message = f"✅ Post {post_info['id']} re-reviewed and approved: {analysis_result.get('explanation', 'Analysis completed')}"

            # Update the stored context
            if self.selected_post_context:
                self.selected_post_context.update({
                    "explanation": analysis_result.get("explanation", ""),
                    "rule_id": analysis_result.get("rule_id"),
                    "violation": analysis_result.get("violation", False)
                })

                if analysis_result.get("confidence") is not None:
                    self.selected_post_context["confidence"] = analysis_result.get("confidence")
                    self.selected_post_context["confidence_level"] = analysis_result.get("confidence_level", "unknown")

        self.event_bus.publish("post_re_reviewed_with_context", {
            "post_id": post_info["id"],
            "result": analysis_result,
            "override_rules": override_rules,
            "contextual_instruction": contextual_instruction
        })

        result = {
            "approved_posts": [] if analysis_result.get("violation") else [post_info],
            "flagged_posts": [post_info] if analysis_result.get("violation") else [],
            "message": message,
            "type": "moderation_action" if actions_taken else "feedback",
            "actions_taken": actions_taken,
            "tool_result": tool_result
        }

        # Add TUI-compatible fields for moderation actions
        if actions_taken:
            if "approve_post" in actions_taken:
                result["action"] = "approve"
                result["post_id"] = post_info["id"]
            elif "reject_post" in actions_taken:
                result["action"] = "reject"
                result["post_id"] = post_info["id"]
            elif "flag_post" in actions_taken:
                result["action"] = "flag"
                result["post_id"] = post_info["id"]

        return result

    def _approve_post(self, post_id: str, reason: str) -> Dict[str, Any]:
        tool_call = ToolCall("approve_post", {"post_id": post_id, "reason": reason})
        result = tool_call.execute()
        self.tool_call_history.append(tool_call)

        with self._lock:
            if post_id in self.todo_posts:
                post = self.todo_posts.pop(post_id)
                self.approved_posts[post_id] = post
                self.selected_post_id = None
                self.selected_post_context = None

        return {
            "approved_posts": [],
            "flagged_posts": [],
            "tool_result": result,
            "message": f"Post {post_id} approved successfully"
        }

    def _reject_post(self, post_id: str, reason: str) -> Dict[str, Any]:
        tool_call = ToolCall("reject_post", {"post_id": post_id, "reason": reason})
        result = tool_call.execute()
        self.tool_call_history.append(tool_call)

        with self._lock:
            if post_id in self.todo_posts:
                self.todo_posts.pop(post_id)
                self.selected_post_id = None
                self.selected_post_context = None

        return {
            "approved_posts": [],
            "flagged_posts": [],
            "tool_result": result,
            "message": f"Post {post_id} rejected successfully"
        }

    def _re_review_selected_post(self, override_rules: List[str], data_loader) -> Dict[str, Any]:
        selected_post = self.get_selected_post()
        if not selected_post:
            return {"approved_posts": [], "flagged_posts": [], "message": "No post selected"}

        data = data_loader.get_formatted_data()

        for post in data["posts"]:
            if post.get("id") == self.selected_post_id:
                mcp_envelope = MCPEnvelope(
                    post=post,
                    subreddit=data["subreddit_name"],
                    rules=data["rules"],
                    review_target="post"
                )
                if override_rules:
                    mcp_envelope.add_override_rules(override_rules)

                analysis_result = self.post_agent.review(mcp_envelope)
                post_info = self._create_post_info(post, analysis_result)

                actions_taken = []
                tool_result = None

                with self._lock:
                    if analysis_result.get("violation"):
                        self.todo_posts[post_info["id"]] = post_info
                        self.approved_posts.pop(post_info["id"], None)
                        message = f"Re-reviewed post {self.selected_post_id}: Still flagged - {analysis_result.get('explanation', 'Analysis completed')}"
                    else:
                        self.approved_posts[post_info["id"]] = post_info
                        self.todo_posts.pop(post_info["id"], None)

                        # Execute approve_post tool since re-review shows no violation
                        tool_call = ToolCall("approve_post", {
                            "post_id": self.selected_post_id,
                            "reason": f"Re-reviewed with override rules: {analysis_result.get('explanation', 'No violations found')}"
                        })
                        tool_result = tool_call.execute()
                        self.tool_call_history.append(tool_call)
                        actions_taken.append("approve_post")

                        # Clear selection after approval
                        self.selected_post_id = None
                        self.selected_post_context = None

                        message = f"✅ Post {post_info['id']} re-reviewed and approved: {analysis_result.get('explanation', 'Analysis completed')}"



                self.event_bus.publish("post_re_reviewed", {
                    "post_id": post_info["id"],
                    "result": analysis_result,
                    "override_rules": override_rules
                })

                result = {
                    "approved_posts": [] if analysis_result.get("violation") else [post_info],
                    "flagged_posts": [post_info] if analysis_result.get("violation") else [],
                    "message": message,
                    "type": "moderation_action" if actions_taken else "feedback",
                    "actions_taken": actions_taken,
                    "tool_result": tool_result
                }

                # Add TUI-compatible fields for moderation actions
                if actions_taken:
                    if "approve_post" in actions_taken:
                        result["action"] = "approve"
                        result["post_id"] = post_info["id"]
                    elif "reject_post" in actions_taken:
                        result["action"] = "reject"
                        result["post_id"] = post_info["id"]
                    elif "flag_post" in actions_taken:
                        result["action"] = "flag"
                        result["post_id"] = post_info["id"]

                return result

        return {"approved_posts": [], "flagged_posts": [], "message": "Selected post not found in data"}

    def _auto_review_posts(self, data_loader, override_rules: Optional[List[str]] = None) -> Dict[str, Any]:
        data = data_loader.get_formatted_data()
        approved_posts = []
        flagged_posts = []

        for post in data["posts"]:
            mcp_envelope = MCPEnvelope(
                post=post,
                subreddit=data["subreddit_name"],
                rules=data["rules"],
                review_target="post"
            )
            if override_rules:
                mcp_envelope.add_override_rules(override_rules)

            analysis_result = self.post_agent.review(mcp_envelope)
            post_info = self._create_post_info(post, analysis_result)

            if analysis_result.get("violation"):
                flagged_posts.append(post_info)
            else:
                approved_posts.append(post_info)

        with self._lock:
            for post in approved_posts:
                self.approved_posts[post["id"]] = post
            for post in flagged_posts:
                self.todo_posts[post["id"]] = post

        return {"approved_posts": approved_posts, "flagged_posts": flagged_posts}

    def _create_post_info(self, post: Dict[str, Any], analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        post_info = {
            "id": post.get("id", ""),
            "title": post.get("title", "")[:150],
            "body": post.get("body", "")[:1000],
            "rule_id": analysis_result.get("rule_id"),
            "violation": analysis_result.get("violation"),
            "explanation": analysis_result.get("explanation")
        }

        # Add confidence information if available
        if analysis_result.get("confidence") is not None:
            post_info["confidence"] = analysis_result.get("confidence")
            post_info["confidence_level"] = analysis_result.get("confidence_level", "unknown")

        # Preserve existing override rules from current post storage
        post_id = post.get("id", "")
        existing_post = self.todo_posts.get(post_id) or self.approved_posts.get(post_id)
        if existing_post and "override_rules" in existing_post:
            post_info["override_rules"] = existing_post["override_rules"]
        elif post.get("override_rules"):
            post_info["override_rules"] = post["override_rules"]

        return post_info

    def get_posts_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "approved_count": len(self.approved_posts),
                "todo_count": len(self.todo_posts),
                "selected_post_id": self.selected_post_id,
                "selected_post_context": self.selected_post_context,
                "approved_posts": list(self.approved_posts.values()),
                "todo_posts": list(self.todo_posts.values()),
                "tool_call_count": len(self.tool_call_history)
            }

    def get_conversation_summary(self) -> Dict[str, Any]:
        return self.conversation_orchestrator.get_conversation_summary()
