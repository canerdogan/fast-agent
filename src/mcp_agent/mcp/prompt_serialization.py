"""
Utilities for converting between different prompt message formats.

This module provides utilities for converting between delimited text formats
and PromptMessageMultipart objects. It includes functionality for:
- Converting delimited text (---USER, ---ASSISTANT) to PromptMessageMultipart
- Converting PromptMessageMultipart objects to delimited text
- Handling MIME types appropriately across different formats
- Supporting resource references with the ---RESOURCE delimiter
"""

from typing import List
from mcp.types import TextContent, EmbeddedResource, TextResourceContents

from mcp_agent.mcp.prompt_message_multipart import PromptMessageMultipart


def multipart_messages_to_delimited_format(
    messages: List[PromptMessageMultipart],
    user_delimiter: str = "---USER",
    assistant_delimiter: str = "---ASSISTANT",
    resource_delimiter: str = "---RESOURCE",
) -> List[str]:
    """
    Convert a list of PromptMessageMultipart objects to delimited format for saving.

    Args:
        messages: List of PromptMessageMultipart objects
        user_delimiter: The delimiter to use for user messages
        assistant_delimiter: The delimiter to use for assistant messages
        resource_delimiter: The delimiter to use for resource references

    Returns:
        A list of strings in delimited format suitable for saving to a file
    """
    delimited_content = []

    for message in messages:
        # Add role delimiter
        if message.role == "user":
            delimited_content.append(user_delimiter)
        elif message.role == "assistant":
            delimited_content.append(assistant_delimiter)
        elif message.role == "system":
            # Skip system messages - MCP only supports user and assistant roles
            continue
        else:
            # Skip other unsupported roles
            continue

        # Process content parts - separate text and resources
        text_parts = []
        resources = []

        for content in message.content:
            if content.type == "text":
                # Regular text content
                text_parts.append(content.text)
            elif content.type == "resource" and hasattr(content, "resource"):
                # Get resource URI if available
                if hasattr(content.resource, "uri"):
                    uri = content.resource.uri
                    # Strip the resource:// prefix if present
                    if str(uri).startswith("resource://"):
                        uri = str(uri).replace("resource://", "", 1)
                    resources.append(str(uri))

                # If the resource has text, add it to the text parts
                if hasattr(content.resource, "text"):
                    text_parts.append(content.resource.text)
            elif content.type == "image":
                # For images, we'll add a placeholder - in practice, we would need proper
                # serialization strategy (possibly base64 encoding or file references)
                text_parts.append("[IMAGE]")

        # Add all text content first
        if text_parts:
            message_text = "\n\n".join(text_parts)
            delimited_content.append(message_text)
        else:
            # Ensure we have at least some content after the role delimiter
            delimited_content.append("")

        # Add resource references after the text content
        for resource in resources:
            delimited_content.append(resource_delimiter)
            delimited_content.append(resource)

    return delimited_content


# TODO: UNUSED - replace with resource handler code.
def delimited_format_to_multipart_messages(
    content: str,
    user_delimiter: str = "---USER",
    assistant_delimiter: str = "---ASSISTANT",
    resource_delimiter: str = "---RESOURCE",
) -> List[PromptMessageMultipart]:
    """
    Parse delimited content into a list of PromptMessageMultipart objects.

    Args:
        content: The delimited content string to parse
        user_delimiter: The delimiter for user messages
        assistant_delimiter: The delimiter for assistant messages
        resource_delimiter: The delimiter for resource references

    Returns:
        A list of PromptMessageMultipart objects
    """
    lines = content.split("\n")
    messages = []

    current_role = None
    current_content = []
    current_resources = []
    expecting_resource_path = False

    for line in lines:
        line_stripped = line.strip()

        # Handle role delimiters
        if line_stripped == user_delimiter:
            # Save previous message if it exists
            if current_role is not None and (current_content or current_resources):
                content_parts = []

                # Add text content if there is any
                if current_content:
                    content_parts.append(
                        TextContent(
                            type="text", text="\n".join(current_content).strip()
                        )
                    )

                # Add resources if there are any
                for resource_path in current_resources:
                    content_parts.append(
                        EmbeddedResource(
                            type="resource",
                            resource=TextResourceContents(
                                uri=f"resource://{resource_path}",
                                mimeType="text/plain",  # Default MIME type, should be inferred
                                text=f"Content of {resource_path}",
                            ),
                        )
                    )

                messages.append(
                    PromptMessageMultipart(
                        role=current_role,
                        content=content_parts,
                    )
                )

            # Start a new user message
            current_role = "user"
            current_content = []
            current_resources = []
            expecting_resource_path = False

        elif line_stripped == assistant_delimiter:
            # Save previous message if it exists
            if current_role is not None and (current_content or current_resources):
                content_parts = []

                # Add text content if there is any
                if current_content:
                    content_parts.append(
                        TextContent(
                            type="text", text="\n".join(current_content).strip()
                        )
                    )

                # Add resources if there are any
                for resource_path in current_resources:
                    content_parts.append(
                        EmbeddedResource(
                            type="resource",
                            resource=TextResourceContents(
                                uri=f"resource://{resource_path}",
                                mimeType="text/plain",  # Default MIME type, should be inferred
                                text=f"Content of {resource_path}",
                            ),
                        )
                    )

                messages.append(
                    PromptMessageMultipart(
                        role=current_role,
                        content=content_parts,
                    )
                )

            # Start a new assistant message
            current_role = "assistant"
            current_content = []
            current_resources = []
            expecting_resource_path = False

        # Handle resource delimiter
        elif line_stripped == resource_delimiter:
            # Next line should be a resource path
            expecting_resource_path = True

        # Handle resource path after the resource delimiter
        elif expecting_resource_path:
            # This line should be a resource path
            current_resources.append(line_stripped)
            expecting_resource_path = False

        # Regular content line
        elif current_role is not None and not expecting_resource_path:
            # Add to current message content
            current_content.append(line)

    # Add the final message if it exists
    if current_role is not None and (current_content or current_resources):
        content_parts = []

        # Add text content if there is any
        if current_content:
            content_parts.append(
                TextContent(type="text", text="\n".join(current_content).strip())
            )

        # Add resources if there are any
        for resource_path in current_resources:
            content_parts.append(
                EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=f"resource://{resource_path}",
                        mimeType="text/plain",  # Default MIME type, should be inferred
                        text=f"Content of {resource_path}",
                    ),
                )
            )

        messages.append(
            PromptMessageMultipart(
                role=current_role,
                content=content_parts,
            )
        )

    return messages


def save_messages_to_delimited_file(
    messages: List["PromptMessageMultipart"],
    file_path: str,
    user_delimiter: str = "---USER",
    assistant_delimiter: str = "---ASSISTANT",
    resource_delimiter: str = "---RESOURCE",
) -> None:
    """
    Save a list of PromptMessageMultipart objects to a file in delimited format.

    Args:
        messages: List of PromptMessageMultipart objects to save
        file_path: Path to the file to write
        user_delimiter: The delimiter to use for user messages
        assistant_delimiter: The delimiter to use for assistant messages
        resource_delimiter: The delimiter to use for resource references
    """
    delimited_content = multipart_messages_to_delimited_format(
        messages,
        user_delimiter,
        assistant_delimiter,
        resource_delimiter=resource_delimiter,
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(delimited_content))


# TODO: UNUSED - replace with resource handlers
def load_messages_from_delimited_file(
    file_path: str,
    user_delimiter: str = "---USER",
    assistant_delimiter: str = "---ASSISTANT",
    resource_delimiter: str = "---RESOURCE",
) -> List["PromptMessageMultipart"]:
    """
    Load a list of PromptMessageMultipart objects from a delimited format file.

    Args:
        file_path: Path to the file to read
        user_delimiter: The delimiter to use for user messages
        assistant_delimiter: The delimiter to use for assistant messages
        resource_delimiter: The delimiter to use for resource references

    Returns:
        A list of PromptMessageMultipart objects
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    return delimited_format_to_multipart_messages(
        content,
        user_delimiter,
        assistant_delimiter,
        resource_delimiter=resource_delimiter,
    )
