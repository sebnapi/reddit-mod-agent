from abc import ABC, abstractmethod
from typing import Dict, Any, List
import json
from datetime import datetime
from openai import OpenAI


class BaseAgent(ABC):
    def __init__(self, model="gpt-4o-mini", temperature: float = 0, max_tokens: int=500):
        self.client = OpenAI()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.response_format = {"type": "json_object"}

    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    @abstractmethod
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def _make_api_call(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format=self.response_format
            )
            content = response.choices[0].message.content.strip()
            return self._parse_response(content)
        except Exception as e:
            return self._handle_error(e)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "error": True,
                "message": f"Invalid JSON response: {content}"
            }

    def _handle_error(self, error: Exception) -> Dict[str, Any]:
        return {
            "error": True,
            "message": str(error)
        }


class EventBus:
    def __init__(self):
        self._subscribers = {}

    def subscribe(self, event_type: str, callback):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def publish(self, event_type: str, data: Dict[str, Any]):
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    # print(f"Error in event callback: {e}")
                    pass

    def unsubscribe(self, event_type: str, callback):
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
            except ValueError:
                pass


class ToolCall:
    def __init__(self, tool_name: str, parameters: Dict[str, Any]):
        self.tool_name = tool_name
        self.parameters = parameters
        self.result = None
        self.executed = False

    def execute(self) -> Dict[str, Any]:
        current_timestamp = datetime.now().isoformat()

        if self.tool_name == "approve_post":
            self.result = {
                "success": True,
                "message": f"Post {self.parameters.get('post_id')} approved successfully",
                "action": "approved",
                "timestamp": current_timestamp
            }
        elif self.tool_name == "reject_post":
            self.result = {
                "success": True,
                "message": f"Post {self.parameters.get('post_id')} rejected with reason: {self.parameters.get('reason', 'No reason provided')}",
                "action": "rejected",
                "timestamp": current_timestamp
            }
        elif self.tool_name == "flag_for_review":
            self.result = {
                "success": True,
                "message": f"Post {self.parameters.get('post_id')} flagged for human review",
                "action": "flagged",
                "timestamp": current_timestamp
            }
        else:
            self.result = {
                "success": False,
                "message": f"Unknown tool: {self.tool_name}"
            }

        self.executed = True
        return self.result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "result": self.result,
            "executed": self.executed
        }