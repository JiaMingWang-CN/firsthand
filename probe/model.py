"""Empirical OpenAI-compatible model probes, with unpredictable test answers."""

import argparse
import asyncio
import base64
import io
import json
import secrets
import time
from pathlib import Path

from openai import AsyncOpenAI
from PIL import Image, ImageDraw, ImageFont

from core.llm import create
from core.runtime import error_summary, llm_api, require, settings, write_json

# Whole-request limit per probe; a normal vision check takes up to about 50s.
PROBE_DEADLINE = 90


def image_challenge():
    answer = " ".join(str(secrets.randbelow(900) + 100) for _ in range(3))
    image = Image.new("RGB", (600, 120), "white")
    ImageDraw.Draw(image).text((20, 30), answer, fill="black", font=ImageFont.load_default(size=45))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return answer, output.getvalue()


def tool_definition(name):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Return the supplied token unchanged.",
            "parameters": {
                "type": "object", "properties": {"token": {"type": "string"}},
                "required": ["token"], "additionalProperties": False,
            },
        },
    }


def valid_calls(message, expected, token):
    calls = message.tool_calls or []
    try:
        return len(calls) == len(expected) and {call.function.name for call in calls} == set(expected) and all(
            json.loads(call.function.arguments) == {"token": token} for call in calls
        )
    except (ValueError, AttributeError):
        return False


async def probe_model(config, run_dir):
    require(config, "base_url", "api_key", "model")
    profile = {
        "model": config["model"], "base_url": config["base_url"], "ready": False,
        "thinking_type": config.get("thinking_type"), "api": llm_api(config),
        "checks": {}, "video": {"status": "not_tested", "fallback": "screenshot_sequence"},
        "audio": {"status": "not_tested", "reason": "No audio product supplied for phase zero"},
    }
    run_dir = Path(run_dir)
    async with AsyncOpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=60, max_retries=0) as client:
        async def check(name, messages, validate, **kwargs):
            started = time.monotonic()
            result = {"supported": False}
            try:
                message, result["usage"] = await create(client, config, messages, 512, PROBE_DEADLINE, name, **kwargs)
                result["supported"] = bool(validate(message))
            except Exception as error:
                result["error"] = error_summary(error, run_dir)
            result["latency_seconds"] = round(time.monotonic() - started, 3)
            profile["checks"][name] = result
            print(f"{name}: {'PASS' if result['supported'] else 'FAIL'}", flush=True)
            return result["supported"]

        token = secrets.token_hex(8)
        await check("conversation", [{"role": "user", "content": f"Reply with exactly {token}"}],
                    lambda message: (message.content or "").strip() == token)
        for name, forced in [("tool_call", False), ("forced_tool", True)]:
            options = {"tools": [tool_definition("echo")]}
            if forced:
                options["tool_choice"] = {"type": "function", "function": {"name": "echo"}}
            await check(name, [{"role": "user", "content": f"Call echo with token {token}. Do not answer in text."}],
                        lambda message: valid_calls(message, ["echo"], token), **options)
        await check("parallel_tools", [{"role": "user", "content": f"Call both echo_a and echo_b in one turn, each with token {token}."}],
                    lambda message: valid_calls(message, ["echo_a", "echo_b"], token),
                    tools=[tool_definition("echo_a"), tool_definition("echo_b")], parallel_tool_calls=True)
        schema = {"type": "object", "properties": {"token": {"type": "string"}},
                  "required": ["token"], "additionalProperties": False}

        def valid_json(message):
            try:
                return json.loads(message.content or "") == {"token": token}
            except ValueError:
                return False

        await check("json_schema", [{"role": "user", "content": f'Return a JSON object with token "{token}".'}],
                    valid_json, json_schema={"name": "probe", "strict": True, "schema": schema})
        # Verify prompt-constrained JSON too, so the fallback has evidence.
        await check("json_prompt", [{"role": "user", "content": f'Return only valid JSON: {{"token":"{token}"}}'}], valid_json)
        for index in range(2):
            answer, png = image_challenge()
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / f"vision_challenge_{index}.png").write_bytes(png)
            await check(f"vision_{index}", [{"role": "user", "content": [
                {"type": "text", "text": "Read the three numbers in the image. Reply only with those numbers separated by spaces."},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
            ]}], lambda message, expected=answer: " ".join((message.content or "").split()) == expected)
        # These samples establish a tested lower bound, not the model's maximum context.
        for size in [2048, 8192, 32768]:
            padding = "sample " * (size // 7)
            await check(f"context_{size}_chars", [{"role": "user", "content": f"Remember token {token}.\n{padding}\nReturn only the token from the beginning."}],
                        lambda message: (message.content or "").strip() == token)
        await asyncio.gather(*(check(f"concurrent_{index}", [{"role": "user", "content": f"Reply with exactly {token}"}],
                              lambda message: (message.content or "").strip() == token) for index in range(10)))
    required = ["conversation", "tool_call", "vision_0", "vision_1"]
    profile["ready"] = all(profile["checks"][name]["supported"] for name in required)
    profile["structured_output"] = "json_schema" if profile["checks"]["json_schema"]["supported"] else "prompt_with_validation"
    profile["recommended_concurrency"] = 10 if all(profile["checks"][f"concurrent_{i}"]["supported"] for i in range(10)) else 1
    write_json(run_dir / "capability_profile.json", profile)
    return profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        profile = asyncio.run(probe_model(settings(), args.run_dir))
    except Exception as error:
        write_json(args.run_dir / "model_error.json", error_summary(error, args.run_dir))
        raise SystemExit(1)
    raise SystemExit(0 if profile["ready"] else 1)


if __name__ == "__main__":
    main()
