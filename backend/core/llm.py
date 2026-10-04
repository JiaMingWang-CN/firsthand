"""Send one request over Chat Completions or the Responses API, chosen by LLM_API."""

import json
from types import SimpleNamespace

from core.limits import async_slot
from core.providers import get_adapter, llm_api
from core.runtime import with_deadline
from core.usage import measured_request


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
                 parallel_tool_calls=None, json_schema=None, json_object=False):
    """Return (message, usage); message exposes .content and .tool_calls[].function.name/.arguments on both APIs.

    json_schema is {"name", "schema", "strict"}; tool definitions and tool_choice use the Chat Completions shape.
    """
    options = {key: value for key, value in [("tools", tools), ("tool_choice", tool_choice),
                                             ("parallel_tool_calls", parallel_tool_calls)] if value is not None}
    api = llm_api(config)
    adapter = get_adapter(config)
    options.update(adapter.thinking_options(api, config.get("thinking_type")))
    options.update(adapter.output_options(api, json_schema, json_object))
    if json_schema and not adapter.supports_json_schema(api):
        messages = [{"role": "system", "content": "Return only JSON satisfying this schema: "
                     + json.dumps(json_schema["schema"], ensure_ascii=False)}, *messages]
    async def send(request):
        # Queue time does not consume the provider request's deadline.
        async with async_slot(config):
            return await with_deadline(lambda: measured_request(request, api, config["model"]), deadline, label)
    if llm_api(config) == "chat_completions":
        response = await send(lambda: client.chat.completions.create(
            model=config["model"], messages=messages, max_tokens=max_tokens, **options,
        ))
        return response.choices[0].message, response.usage.model_dump() if response.usage else None
    if tools:
        options["tools"] = [response_tool(tool) for tool in tools]
    if tool_choice:
        options["tool_choice"] = {"type": "function", "name": tool_choice["function"]["name"]}
    response = await send(lambda: client.responses.create(
        model=config["model"], input=[{"role": message["role"], "content": response_content(message["content"])} for message in messages],
        max_output_tokens=max_tokens, **options,
    ))
    calls = [SimpleNamespace(function=SimpleNamespace(name=item.name, arguments=item.arguments))
             for item in response.output if item.type == "function_call"]
    message = SimpleNamespace(content=response.output_text, tool_calls=calls or None)
    return message, response.usage.model_dump() if response.usage else None
