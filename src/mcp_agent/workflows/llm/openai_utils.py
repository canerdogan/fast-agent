"""
Utility functions for OpenAI integration with MCP.

This file provides backward compatibility with the existing API while
delegating to the proper implementations in the providers/ directory.
"""

from typing import Dict, Any, Union

from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageParam,
)

from mcp_agent.mcp.prompt_message_multipart import PromptMessageMultipart
from mcp_agent.workflows.llm.providers.openai_multipart import (
    openai_to_multipart,
    multipart_to_openai,
)


def openai_message_to_prompt_message_multipart(
    message: Union[ChatCompletionMessage, Dict[str, Any]],
) -> PromptMessageMultipart:
    """
    Convert an OpenAI ChatCompletionMessage to a PromptMessageMultipart.

    Args:
        message: The OpenAI message to convert (can be an actual ChatCompletionMessage
                or a dictionary with the same structure)

    Returns:
        A PromptMessageMultipart representation
    """
    return openai_to_multipart(message)


def openai_message_param_to_prompt_message_multipart(
    message_param: ChatCompletionMessageParam,
) -> PromptMessageMultipart:
    """
    Convert an OpenAI ChatCompletionMessageParam to a PromptMessageMultipart.

    Args:
        message_param: The OpenAI message param to convert

    Returns:
        A PromptMessageMultipart representation
    """
    return openai_to_multipart(message_param)


def prompt_message_multipart_to_openai_message_param(
    multipart: PromptMessageMultipart,
) -> ChatCompletionMessageParam:
    """
    Convert a PromptMessageMultipart to an OpenAI ChatCompletionMessageParam.

    Args:
        multipart: The PromptMessageMultipart to convert

    Returns:
        An OpenAI ChatCompletionMessageParam representation
    """
    return multipart_to_openai(multipart)
