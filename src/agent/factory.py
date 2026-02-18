from __future__ import annotations

from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.models.aws import AwsBedrock
from agno.models.google import Gemini

from src.agent.prompts import (
    EVOLUTION_PROMPT,
    ONBOARD_SYSTEM_PROMPT,
    get_comment_prompt,
    get_review_prompt,
)
from src.agent.tools import make_tools
from src.config import ModelProvider, get_settings
from src.knowledge.store import get_knowledge_base
from src.models import ReviewResponseSchema


def _build_model_for_id(model_id: str):
    s = get_settings()
    match s.model_provider:
        case ModelProvider.ANTHROPIC:
            return Claude(id=model_id, api_key=s.anthropic_api_key)
        case ModelProvider.BEDROCK:
            return AwsBedrock(id=model_id)
        case ModelProvider.GEMINI:
            return Gemini(id=model_id, api_key=s.google_api_key)
        case _:
            raise ValueError(f"Unsupported model provider: {s.model_provider}")


def _build_primary_model():
    return _build_model_for_id(get_settings().primary_model_id)


def _build_standard_model():
    return _build_model_for_id(get_settings().standard_model_id)


def build_classifier_model():
    return _build_model_for_id(get_settings().classifier_model_id)


def create_review_agent(
    repo_full_name: str, installation_id: int, head_ref: str = "HEAD", language: str = "pt-BR"
) -> Agent:
    kb = get_knowledge_base(repo_full_name)
    tools = make_tools(installation_id, repo_full_name, default_ref=head_ref)
    return Agent(
        name="louro-reviewer",
        model=_build_primary_model(),
        instructions=get_review_prompt(language),
        tools=tools,
        knowledge=kb,
        output_schema=ReviewResponseSchema,
        markdown=True,
    )


def create_comment_agent(
    repo_full_name: str, installation_id: int, head_ref: str = "HEAD", language: str = "pt-BR"
) -> Agent:
    kb = get_knowledge_base(repo_full_name)
    tools = make_tools(installation_id, repo_full_name, default_ref=head_ref)
    return Agent(
        name="comment-responder",
        model=_build_standard_model(),
        instructions=get_comment_prompt(language),
        tools=tools,
        knowledge=kb,
        markdown=True,
    )


def create_onboard_agent(repo_full_name: str, installation_id: int, default_branch: str = "main") -> Agent:
    tools = make_tools(installation_id, repo_full_name, default_ref=default_branch)
    return Agent(
        name="repo-onboarder",
        model=_build_primary_model(),
        instructions=ONBOARD_SYSTEM_PROMPT,
        tools=tools,
        markdown=True,
    )


def create_evolution_agent(repo_full_name: str, installation_id: int, default_branch: str = "main") -> Agent:
    tools = make_tools(installation_id, repo_full_name, default_ref=default_branch)
    return Agent(
        name="evolution-analyzer",
        model=_build_primary_model(),
        instructions=EVOLUTION_PROMPT,
        tools=tools,
        markdown=True,
    )
