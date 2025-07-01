import threading
import time
import random
import os
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional
from agents.base_agent import EventBus
from agents.meta_agent import MetaChatAgent
from data import DataLoader


class BackgroundProcessor:
    def __init__(self, meta_agent: MetaChatAgent, subreddits: List[str], event_bus: Optional[EventBus] = None, interval: int = 10, data_dir: str = "data"):
        self.meta_agent = meta_agent
        self.subreddits = subreddits
        self.event_bus = event_bus or EventBus()
        self.interval = interval
        self.running = False
        self._thread = None
        self.data_dir = Path(data_dir)

        self.processed_posts = set()  # Track processed posts to avoid duplicates

    def start(self):
        if not self.running:
            self.running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            self.event_bus.publish("background_processor_started", {"status": "started"})

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
        self.event_bus.publish("background_processor_stopped", {"status": "stopped"})

    def _run(self):
        while self.running:
            try:
                self._process_batch()
                time.sleep(self.interval)
            except Exception as e:
                self.event_bus.publish("background_processor_error", {"error": str(e)})
                time.sleep(self.interval)

    def _process_batch(self):
        try:
            selected_posts = self._get_random_posts()
            if not selected_posts:
                return

            for subreddit_name, post_ids in selected_posts.items():
                if post_ids:
                    data_loader = DataLoader(
                        data_dir=str(self.data_dir),
                        subreddit_name=subreddit_name,
                        post_ids=post_ids
                    )

                    result = self.meta_agent.interact("Auto check posts", data_loader)

                    self.event_bus.publish("background_posts_loaded", {
                        "approved_posts": result.get("approved_posts", []),
                        "flagged_posts": result.get("flagged_posts", []),
                        "batch_size": len(result.get("approved_posts", []) + result.get("flagged_posts", [])),
                        "timestamp": time.time(),
                        "subreddit": subreddit_name
                    })

        except Exception as e:
            self.event_bus.publish("background_processing_error", {"error": str(e)})

    def _get_available_posts(self, subreddit_name: str) -> List[str]:
        """Get all available post IDs from a subreddit directory"""
        subreddit_path = self.data_dir / subreddit_name
        if not subreddit_path.exists():
            return []

        post_ids = []
        for item in subreddit_path.iterdir():
            if item.is_dir() and item.name not in ['__pycache__']:
                post_ids.append(item.name)

        return post_ids

    def _get_random_posts(self) -> Dict[str, List[str]]:
        """Get random posts from both regular and violation subreddits"""
        selected_posts = {}

        for subreddit in self.subreddits:
            # Get posts from regular subreddit
            regular_posts = self._get_available_posts(subreddit)
            violation_posts = self._get_available_posts(f"Viol_{subreddit}")

            # Randomly select 1-2 posts from each type
            if regular_posts:
                num_regular = random.randint(0, min(2, len(regular_posts)))
                if num_regular > 0:
                    selected_regular = random.sample(regular_posts, num_regular)
                    # Filter out already processed posts
                    new_regular = [p for p in selected_regular if f"{subreddit}:{p}" not in self.processed_posts]
                    if new_regular:
                        selected_posts[subreddit] = new_regular
                        # Mark as processed
                        for post_id in new_regular:
                            self.processed_posts.add(f"{subreddit}:{post_id}")

            if violation_posts:
                num_violation = random.randint(0, min(2, len(violation_posts)))
                if num_violation > 0:
                    selected_violation = random.sample(violation_posts, num_violation)
                    # Filter out already processed posts
                    new_violation = [p for p in selected_violation if f"Viol_{subreddit}:{p}" not in self.processed_posts]
                    if new_violation:
                        selected_posts[f"Viol_{subreddit}"] = new_violation
                        # Mark as processed
                        for post_id in new_violation:
                            self.processed_posts.add(f"Viol_{subreddit}:{post_id}")

        # Clear processed posts periodically to allow re-processing
        if len(self.processed_posts) > 100:
            self.processed_posts.clear()

        return selected_posts


class MockDataLoader:
    def __init__(self, mock_data: Dict[str, Any]):
        self.mock_data = mock_data

    def get_formatted_data(self) -> Dict[str, Any]:
        return self.mock_data

    def load_raw_data(self):
        return self.mock_data


class EventProcessor:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.setup_event_handlers()

    def setup_event_handlers(self):
        self.event_bus.subscribe("post_selected", self._handle_post_selected)
        self.event_bus.subscribe("post_approved", self._handle_post_approved)
        self.event_bus.subscribe("post_rejected", self._handle_post_rejected)
        self.event_bus.subscribe("tool_executed", self._handle_tool_executed)
        self.event_bus.subscribe("background_posts_loaded", self._handle_background_posts)

    def _handle_post_selected(self, data: Dict[str, Any]):
        post_id = data.get("post_id")
        # print(f"[EVENT] Post selected: {post_id}")

    def _handle_post_approved(self, data: Dict[str, Any]):
        post_id = data.get("post_id")
        result = data.get("result", {})
        # print(f"[EVENT] Post approved: {post_id} - {result.get('message', '')}")

    def _handle_post_rejected(self, data: Dict[str, Any]):
        post_id = data.get("post_id")
        result = data.get("result", {})
        # print(f"[EVENT] Post rejected: {post_id} - {result.get('message', '')}")

    def _handle_tool_executed(self, data: Dict[str, Any]):
        tool_call = data.get("tool_call", {})
        tool_name = tool_call.get("tool_name", "")
        # print(f"[EVENT] Tool executed: {tool_name}")

    def _handle_background_posts(self, data: Dict[str, Any]):
        approved_count = len(data.get("approved_posts", []))
        flagged_count = len(data.get("flagged_posts", []))
        # print(f"[EVENT] Background processing: {approved_count} approved, {flagged_count} flagged")