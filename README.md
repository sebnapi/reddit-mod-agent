# Weekend project: Reddit Moderation Agent

AI-powered Reddit moderation prototype with a terminal UI. Automatically reviews posts using LLM agents and provides an interactive interface for human moderators. Uses an event-driven system for real-time agent communication and UI updates (mimicking a Kafka streaming use case).

## Showcase

https://github.com/user-attachments/assets/7b52ae24-9391-4a35-8c94-f8acb607fed7

## Quick Start

To run the TUI make sure your terminal is **at least 153 x 50 large.**

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp env.example .env
# Add your OPENAI_API_KEY to .env

# Run
python src/tui.py
```

## Features

- **Multi-Agent Architecture**: Specialized agents for different tasks (moderation, conversation, confidence scoring)
- **Interactive TUI**: Terminal-based interface with real-time post management
- **Context-Aware**: Remembers conversation state and post selection
- **Override Rules**: Extract and apply custom moderation rules on-the-fly
- **Background Processing**: Automatically reviews posts in the background
- **Event-Driven**: Real-time updates via event bus system

## Files

```
src/
├── agents/                 # AI agent system
│   ├── meta_agent.py      # Main orchestrator
│   ├── conversation_orchestrator.py  # Routes user input
│   ├── post_agent.py      # Post-specific analysis
│   ├── confidence_rule_agent.py  # Confidence scoring
│   └── override_rules_extraction.py  # Custom rule extraction
├── tui.py                 # Terminal UI
├── background_processor.py # Background post processing
└── data.py               # Data loading utilities
```

## Usage

- **Select posts** with ENTER from the right panels
- **Chat naturally** with the AI about moderation decisions
- **Override rules** by explaining exceptions to the AI
- **Approve/Reject rules** through the chat
- **Exit** with `/exit`
