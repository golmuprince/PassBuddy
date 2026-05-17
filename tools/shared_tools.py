from langgraph.types import Command
from langchain_core.tools import tool

@tool
def transfer_to_agent(agent_name: str):
    """
    다른 에이전트로 전환합니다.
    Args:
        agent_name: 전환할 에이전트 이름
        'planner_agent', 'class_agent', 'quiz_agent' 중 하나
    """
    return Command(
        goto=agent_name,
        graph=Command.PARENT,
        update={
            "current_agent": agent_name,
        },
    )