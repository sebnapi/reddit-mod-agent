import npyscreen
import threading
import time
import curses.ascii
from agents.meta_agent import MetaChatAgent
from agents.post_agent import PostSpecificAgent
from agents.override_rules_extraction import OverrideRuleExtractor
from agents.base_agent import EventBus
from background_processor import BackgroundProcessor, EventProcessor
from data import DataLoader

class ChatInput(npyscreen.Textfield):
    def __init__(self, screen, parent_form, *args, **kwargs):
        self.parent_form = parent_form
        super().__init__(screen, *args, **kwargs)
        self.set_up_handlers()

    def set_up_handlers(self):
        super().set_up_handlers()
        # Override Enter to send message
        self.handlers[13] = self.h_send_message
        self.handlers[curses.ascii.CR] = self.h_send_message
        self.handlers[10] = self.h_send_message  # Also handle line feed

    def h_send_message(self, inp):
        # Send the message
        self.parent_form.handle_message_send()
        return True

class SelectablePostList(npyscreen.BoxTitle):
    _contained_widget = npyscreen.MultiLineAction

    def __init__(self, screen, parent_form, *args, **kwargs):
        self.parent_form = parent_form
        super().__init__(screen, *args, **kwargs)
        self.entry_widget.parent_form = parent_form
        self.entry_widget.actionHighlighted = self.actionHighlighted

    def actionHighlighted(self, act_on_this, key_press):
        if act_on_this and len(act_on_this) > 0:
            post_id = act_on_this.split(' | ')[0].replace('► ', '').replace('  ', '')
            self.parent_form.select_post(post_id)

class MainForm(npyscreen.FormBaseNew):
    def __init__(self, *args, **kwargs):
        self.meta_agent: MetaChatAgent = kwargs.pop('meta_agent', None)
        self.data_loader_factory = kwargs.pop('data_loader_factory', None)
        self.event_bus: EventBus = kwargs.pop('event_bus', None)
        self.background_processor: BackgroundProcessor = kwargs.pop('background_processor', None)
        self.running = True
        super().__init__(*args, **kwargs)

        if self.event_bus:
            self.event_bus.subscribe("background_posts_loaded", self._handle_background_posts)
            self.event_bus.subscribe("tool_executed", self._handle_tool_executed)
            self.event_bus.subscribe("post_approved", self._handle_post_action)
            self.event_bus.subscribe("post_rejected", self._handle_post_action)
            self.event_bus.subscribe("rule_extracted", self._handle_rule_extracted)

    def create(self):
        self.name = "Reddit Moderation Agent"

        # Chat window - 100 columns wide from left
        self.chat_window = self.add(npyscreen.BoxTitle, name="Chat", relx=2, rely=2, max_width=100, max_height=40, scroll_exit=True, editable=False)

        # Input field for chat messages - match chat window width
        self.add(npyscreen.FixedText, value="Message (ENTER to send):", relx=2, rely=43, editable=False)
        self.add(npyscreen.FixedText, value=">", relx=2, rely=44, editable=False)
        self.input_field = self.add(ChatInput, parent_form=self, relx=4, rely=44, max_width=98)

        # Store reference for setting focus
        self.input_field_index = len(self._widgets__) - 1

        # Todo list - right pane, 45 columns wide (now selectable)
        self.todo_box = self.add(SelectablePostList, parent_form=self, name="Posts Requiring Attention (ENTER to select)", relx=105, rely=2, max_width=45, max_height=20, scroll_exit=True)

        # Approved list - right pane, 45 columns wide (now also selectable)
        self.approved_box = self.add(SelectablePostList, parent_form=self, name="Auto Approved Posts (ENTER to select)", relx=105, rely=23, max_width=45, max_height=20, scroll_exit=True)

        self.add_chat_message("Hello, these posts require your attention.")
        self.update_post_panels()

        # Set focus to the input field by default
        self.editw = self.input_field_index

        # Start background processor if available
        if self.background_processor:
            self.background_processor.start()

    def select_post(self, post_id):
        if self.meta_agent:
            self.meta_agent.select_post(post_id)
            if self.meta_agent.selected_post_id == post_id:
                self.add_chat_message(f"Selected post: {post_id}")
            else:
                self.add_chat_message(f"Deselected post: {post_id}")
            self.update_post_panels()

    def handle_message_send(self):
        user_input = self.input_field.value.strip()

        if user_input:
            if user_input == "/exit":
                self.running = False
                if self.background_processor:
                    self.background_processor.stop()
                self.parentApp.setNextForm(None)
                return

            self.add_chat_message(f"You: {user_input}")

            try:
                loader = self.data_loader_factory()
                result = self.meta_agent.interact(user_input, loader)

                self.update_post_panels()

                # Format and display agent response
                self._display_agent_response(result, user_input)

            except Exception as e:
                self.add_chat_message(f"Agent: Error processing request: {str(e)}")

            self.input_field.value = ""
            self.input_field.display()

    def _display_agent_response(self, result, user_input):
        """Display agent response based on conversation orchestrator response type"""

        response_type = result.get("type", "unknown")
        message = result.get("message", "")

        # Handle different response types
        if response_type == "moderation_action":
            action = result.get("action", "unknown")
            post_id = result.get("post_id", "")
            self.add_chat_message(f"✓ Action: {action.title()} post {post_id}")
            if result.get("tool_result"):
                tool_result = result["tool_result"]
                self.add_chat_message(f"  {tool_result.get('message', 'Action completed')}")

        elif response_type == "conversation":
            self.add_chat_message(f"Agent: {message}")

        elif response_type == "query_response":
            self.add_chat_message(f"📊 {message}")
            data_provided = result.get("data_provided", [])
            if data_provided:
                self.add_chat_message(f"  (Data: {', '.join(data_provided)})")
        elif response_type == "feedback":
            self.add_chat_message(f"💬 {message}")
        elif response_type == "system_command":
            # Handle legacy auto-review responses
            approved_count = len(result.get("approved_posts", []))
            flagged_count = len(result.get("flagged_posts", []))
            if approved_count > 0 or flagged_count > 0:
                self.add_chat_message(f"🔍 Auto-review: {approved_count} approved, {flagged_count} flagged")
            else:
                self.add_chat_message(f"⚙️ {message}")

        elif response_type == "error":
            self.add_chat_message(f"Error: {message}")

    def add_chat_message(self, message):
        import textwrap

        # Define max width for chat messages (account for chat window padding)
        max_width = 90

        lines = message.split('\n')
        formatted_lines = []

        for i, line in enumerate(lines):
            # Skip empty lines but preserve them for formatting
            if not line.strip():
                formatted_lines.append("")
                continue

            # Determine if this is a continuation line
            is_continuation = i > 0 and not line.startswith(('You:', 'Agent:', 'Tool Result:', 'Background:'))
            prefix = '    ' if is_continuation else ''

            # Calculate available width after prefix
            available_width = max_width - len(prefix)

            # Word wrap long lines
            if len(line) > available_width:
                wrapped_lines = textwrap.wrap(line, width=available_width)
                for j, wrapped_line in enumerate(wrapped_lines):
                    if j == 0:
                        formatted_lines.append(prefix + wrapped_line)
                    else:
                        # Additional continuation lines get extra indentation
                        formatted_lines.append(prefix + '  ' + wrapped_line)
            else:
                formatted_lines.append(prefix + line)

        # Add all formatted lines to the chat window
        for line in formatted_lines:
            self.chat_window.values.append(line)

        # Keep only last 150 messages to prevent memory issues (increased for better context)
        if len(self.chat_window.values) > 150:
            self.chat_window.values = self.chat_window.values[-150:]

        # Auto-scroll to bottom with ultra-safe bounds checking
        try:
            if hasattr(self.chat_window, 'entry_widget') and self.chat_window.entry_widget and self.chat_window.values:
                widget = self.chat_window.entry_widget
                num_values = len(self.chat_window.values)

                if hasattr(widget, 'height') and hasattr(widget, 'start_display_at') and hasattr(widget, 'cursor_line'):
                    # Ultra-conservative scrolling: only scroll if we have enough content
                    if num_values > widget.height:
                        # Auto-scroll to show latest messages
                        widget.start_display_at = num_values - widget.height
                        widget.cursor_line = num_values - 1
                    else:
                        # Not enough content to scroll, just show from beginning
                        widget.start_display_at = 0
                        widget.cursor_line = max(0, num_values - 1)

            self.chat_window.display()
        except (IndexError, AttributeError):
            try:
                self.chat_window.display()
            except:
                pass

    def update_post_panels(self):
        if not self.meta_agent:
            return

        summary = self.meta_agent.get_posts_summary()

        try:
            todo_values = []
            for post in summary['todo_posts']:
                icon = "► " if post['id'] == summary['selected_post_id'] else "  "
                todo_values.append(f"{icon}{post['id']} | {post['title'][:35]}")
            self.todo_box.values = todo_values
            self.todo_box.display()
        except (IndexError, AttributeError):
            # Skip update if display fails
            pass

        try:
            approved_values = []
            for post in summary['approved_posts']:
                icon = "► " if post['id'] == summary['selected_post_id'] else "  "
                approved_values.append(f"{icon}{post['id']} | {post['title'][:35]}")
            self.approved_box.values = approved_values
            self.approved_box.display()
        except (IndexError, AttributeError):
            # Skip update if display fails
            pass

    def force_ui_refresh(self):
        try:
            self.update_post_panels()
            self.display()
        except Exception:
            pass

    def _handle_background_posts(self, data):
        self.force_ui_refresh()
        approved_count = len(data.get("approved_posts", []))
        flagged_count = len(data.get("flagged_posts", []))

    def _handle_tool_executed(self, data):
        tool_call = data.get("tool_call", {})
        tool_name = tool_call.get("tool_name", "")
        result = tool_call.get("result", {})
        if result.get("success"):
            self.add_chat_message(f"Tool '{tool_name}' executed: {result.get('message', 'Success')}")
        else:
            self.add_chat_message(f"Tool '{tool_name}' failed: {result.get('message', 'Unknown error')}")

    def _handle_post_action(self, data):
        self.update_post_panels()

    def _handle_rule_extracted(self, data):
        rule = data.get("rule")

        if rule:
            self.add_chat_message(f"🔧 Override: {rule}")

    def while_waiting(self):
        pass


class MetaChatTUI(npyscreen.NPSAppManaged):
    def __init__(self, meta_agent: MetaChatAgent, data_loader_factory, event_bus: EventBus, background_processor: BackgroundProcessor):
        self.meta_agent = meta_agent
        self.data_loader_factory = data_loader_factory
        self.event_bus = event_bus
        self.background_processor = background_processor
        super().__init__()

    def onStart(self):
        self.addForm('MAIN', MainForm,
                    meta_agent=self.meta_agent,
                    data_loader_factory=self.data_loader_factory,
                    event_bus=self.event_bus,
                    background_processor=self.background_processor)


def mock_data_loader_factory():
    return DataLoader(data_dir="data", subreddit_name="AskHistorians")


def main():
    event_bus = EventBus()

    post_agent = PostSpecificAgent()
    override_rule_extractor = OverrideRuleExtractor(event_bus=event_bus)

    meta_agent = MetaChatAgent(
        post_agent=post_agent,
        override_rule_extractor=override_rule_extractor,
        event_bus=event_bus
    )

    background_processor = BackgroundProcessor(
        meta_agent=meta_agent,
        subreddits=["AskHistorians"],
        event_bus=event_bus,
        interval=5,
        data_dir="data"
    )

    event_processor = EventProcessor(event_bus)
    app = MetaChatTUI(meta_agent, mock_data_loader_factory, event_bus, background_processor)

    try:
        app.run()
    finally:
        background_processor.stop()


if __name__ == "__main__":
    main()

