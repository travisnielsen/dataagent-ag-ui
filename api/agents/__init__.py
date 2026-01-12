"""
Agents package for the CopilotKit + Microsoft Agent Framework API.

Contains:
- agent.py: Main sample agent with weather and proverb tools
- logistics_agent.py: Logistics dashboard agent with flight payload tools
"""

from agents.agent import create_agent
from agents.logistics_agent import create_logistics_agent

__all__ = ["create_agent", "create_logistics_agent"]
