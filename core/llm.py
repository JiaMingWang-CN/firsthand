"""Send one request over Chat Completions or the Responses API, chosen by LLM_API."""

from types import SimpleNamespace

from core.runtime import llm_api, thinking_body, with_deadline


def response_content(content):
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if part["type"] == "text":
            parts.append({"type": "input_text", "text": part["text"]})
        elif part["type"] == "image_url":
            parts.append({"type": "input_image", "image_url": part["image_url"]["url"], "detail": "auto"})
        else:
            raise ValueError(f"Unsupported message part for the Responses API: {part['type']}")
    return parts


def response_tool(tool):
    function = tool["function"]
    return {"type": "function", "name": function["name"], "description": function.get("description", ""),
            "parameters": function["parameters"], "strict": function.get("strict", False)}


async def create(client, config, messages, max_tokens, deadline, label, *, tools=None, tool_choice=None,
                 parallel_tool_calls=None, json_schema=None):
    """Return (message, usage); message exposes .content and .tool_calls[].function.name/.arguments on both APIs.

    json_schema is {"name", "schema", "strict"}; tool definitions and tool_choice use the Chat Completions shape.
    """
    options = {key: value for key, value in [("tools", tools), ("tool_choice", tool_choice),
                                             ("parallel_tool_calls", parallel_tool_calls)] if value is not None}
    if llm_api(config) == "chat_completions":
        if json_schema:
            options["response_format"] = {"type": "json_schema", "json_schema": json_schema}
        response = await with_deadline(lambda: client.chat.completions.create(
            model=config["model"], messages=messages, max_tokens=max_tokens, extra_body=thinking_body(config), **options,
        ), deadline, label)
        return response.choices[0].message, response.usage.model_dump() if response.usage else None
    if tools:
        options["tools"] = [response_tool(tool) for tool in tools]
    if tool_choice:
        options["tool_choice"] = {"type": "function", "name": tool_choice["function"]["name"]}
    if json_schema:
        options["text"] = {"format": {"type": "json_schema", **json_schema}}
    # The Responses API switches thinking with reasoning.effort rather than the provider's thinking.type body.
    if thinking_body(config).get("thinking") == {"type": "disabled"}:
        options["reasoning"] = {"effort": "none"}
    response = await with_deadline(lambda: client.responses.create(
        model=config["model"], input=[{"role": message["role"], "content": response_content(message["content"])} for message in messages],
        max_output_tokens=max_tokens, **options,
    ), deadline, label)
    calls = [SimpleNamespace(function=SimpleNamespace(name=item.name, arguments=item.arguments))
             for item in response.output if item.type == "function_call"]
    message = SimpleNamespace(content=response.output_text, tool_calls=calls or None)
    return message, response.usage.model_dump() if response.usage else None
