"""
Multi-provider abstraction for openbash.

Translates tool calling between Anthropic, OpenAI (+ xAI), and Gemini APIs.
Each provider has different formats for tools, messages, and streaming — this
module normalizes everything to a common interface.

Usage:
    provider = get_provider("gpt-4o")
    result = provider.stream_with_tools(model, system, messages, tools, max_tokens)
    # result.text, result.tool_calls, result.input_tokens, result.output_tokens
"""

import json
import os


# ── Normalized result ────────────────────────────────────────────

class LLMResult:
    """Normalized result from any provider."""
    __slots__ = ("text", "tool_calls", "input_tokens", "output_tokens", "raw_content")

    def __init__(self):
        self.text = ""
        self.tool_calls = []       # list of ToolCall
        self.input_tokens = 0
        self.output_tokens = 0
        self.raw_content = None    # provider-specific, for building next message

class ToolCall:
    """Normalized tool call."""
    __slots__ = ("id", "name", "input")

    def __init__(self, id, name, input):
        self.id = id
        self.name = name
        self.input = input


# ── Provider interface ───────────────────────────────────────────

class BaseProvider:
    """Base class for LLM providers."""

    def stream_with_tools(self, model, system, messages, tools, max_tokens=16384,
                          on_text=None):
        """Stream a response with tool calling support.

        Args:
            model: model ID string
            system: system prompt string
            messages: list of message dicts (provider-agnostic format)
            tools: list of tool schemas (Anthropic format — will be translated)
            max_tokens: max output tokens
            on_text: callback(text_chunk) for streaming text output

        Returns:
            LLMResult with text, tool_calls, token counts, and raw_content
        """
        raise NotImplementedError

    def build_assistant_message(self, result):
        """Build the assistant message to append to conversation history.
        Returns a dict in the provider's native format."""
        raise NotImplementedError

    def build_tool_results(self, tool_calls_with_results):
        """Build tool result messages to append to conversation history.

        Args:
            tool_calls_with_results: list of (ToolCall, result_string) tuples

        Returns:
            A message dict in the provider's native format.
        """
        raise NotImplementedError

    def test_api(self, model):
        """Quick API test. Returns (input_tokens, output_tokens) or raises."""
        raise NotImplementedError


# ── Anthropic provider ───────────────────────────────────────────

class AnthropicProvider(BaseProvider):

    def __init__(self):
        import anthropic
        self._client = anthropic.Anthropic()
        self._anthropic = anthropic

    def stream_with_tools(self, model, system, messages, tools, max_tokens=16384,
                          on_text=None):
        result = LLMResult()

        with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,  # Anthropic format is our native format
        ) as stream:
            for event in stream:
                if hasattr(event, 'type'):
                    if event.type == "content_block_delta":
                        if hasattr(event, 'delta') and event.delta.type == "text_delta":
                            result.text += event.delta.text
                            if on_text:
                                on_text(event.delta.text)

            final = stream.get_final_message()
            result.input_tokens = final.usage.input_tokens
            result.output_tokens = final.usage.output_tokens
            result.raw_content = final.content

            for block in final.content:
                if block.type == "tool_use":
                    result.tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    ))
                elif block.type == "text" and block.text and not result.text:
                    result.text = block.text

        return result

    def build_assistant_message(self, result):
        return {"role": "assistant", "content": result.raw_content}

    def build_tool_results(self, tool_calls_with_results):
        return {"role": "user", "content": [
            {
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": res,
            }
            for tc, res in tool_calls_with_results
        ]}

    def test_api(self, model):
        resp = self._client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Reply with just: OK"}],
        )
        return resp.usage.input_tokens, resp.usage.output_tokens

    @property
    def api_error(self):
        return self._anthropic.APIError

    @property
    def auth_error(self):
        return self._anthropic.AuthenticationError


# ── OpenAI-compatible provider (OpenAI + xAI) ───────────────────

class OpenAIProvider(BaseProvider):
    """Works with OpenAI and xAI (Grok) — both use the OpenAI API format."""

    def __init__(self, base_url=None, api_key_env="OPENAI_API_KEY"):
        from openai import OpenAI, APIError, AuthenticationError
        self._APIError = APIError
        self._AuthError = AuthenticationError

        kwargs = {}
        if base_url:
            kwargs["base_url"] = base_url
        api_key = os.environ.get(api_key_env, "")
        if api_key:
            kwargs["api_key"] = api_key

        self._client = OpenAI(**kwargs)

    def _convert_tools(self, tools):
        """Convert Anthropic tool format to OpenAI function calling format."""
        oai_tools = []
        for t in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            })
        return oai_tools

    def _convert_messages(self, system, messages):
        """Convert Anthropic message format to OpenAI format."""
        oai_msgs = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user" and isinstance(content, list):
                # Tool results
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        oai_msgs.append({
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": item.get("content", ""),
                        })
                    elif isinstance(item, dict):
                        oai_msgs.append({"role": "user", "content": str(item)})
                continue

            if role == "assistant" and isinstance(content, list):
                # Assistant message with tool calls
                text_parts = []
                tool_calls = []
                for block in content:
                    if hasattr(block, 'type'):
                        # Anthropic native objects
                        if block.type == "text":
                            text_parts.append(block.text)
                        elif block.type == "tool_use":
                            tool_calls.append({
                                "id": block.id,
                                "type": "function",
                                "function": {
                                    "name": block.name,
                                    "arguments": json.dumps(block.input),
                                },
                            })
                    elif isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block.get("input", {})),
                                },
                            })

                msg_dict = {"role": "assistant"}
                if text_parts:
                    msg_dict["content"] = "\n".join(text_parts)
                else:
                    msg_dict["content"] = None
                if tool_calls:
                    msg_dict["tool_calls"] = tool_calls
                oai_msgs.append(msg_dict)
                continue

            oai_msgs.append({"role": role, "content": content if isinstance(content, str) else str(content)})

        return oai_msgs

    def stream_with_tools(self, model, system, messages, tools, max_tokens=16384,
                          on_text=None):
        result = LLMResult()
        oai_tools = self._convert_tools(tools)
        oai_msgs = self._convert_messages(system, messages)

        stream = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=oai_msgs,
            tools=oai_tools,
            stream=True,
            stream_options={"include_usage": True},
        )

        # Accumulate streamed tool calls
        tool_call_accum = {}  # index -> {id, name, arguments}

        for chunk in stream:
            if chunk.usage:
                result.input_tokens = chunk.usage.prompt_tokens or 0
                result.output_tokens = chunk.usage.completion_tokens or 0

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta and delta.content:
                result.text += delta.content
                if on_text:
                    on_text(delta.content)

            if delta and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_accum:
                        tool_call_accum[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_call_accum[idx]["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        tool_call_accum[idx]["name"] = tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        tool_call_accum[idx]["arguments"] += tc_delta.function.arguments

        # Build tool calls from accumulated data
        raw_tool_calls = []
        for idx in sorted(tool_call_accum.keys()):
            tc = tool_call_accum[idx]
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            result.tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], input=args))
            raw_tool_calls.append({
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            })

        # Store raw content for building next message
        result.raw_content = {
            "text": result.text,
            "tool_calls": raw_tool_calls,
        }

        return result

    def build_assistant_message(self, result):
        msg = {"role": "assistant"}
        raw = result.raw_content
        msg["content"] = raw.get("text") or None
        if raw.get("tool_calls"):
            msg["tool_calls"] = raw["tool_calls"]
        return msg

    def build_tool_results(self, tool_calls_with_results):
        # OpenAI expects separate tool messages, but we return them as a list
        # that gets extended into messages
        return [
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": res,
            }
            for tc, res in tool_calls_with_results
        ]

    def test_api(self, model):
        resp = self._client.chat.completions.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Reply with just: OK"}],
        )
        return (resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)

    @property
    def api_error(self):
        return self._APIError

    @property
    def auth_error(self):
        return self._AuthError


class XAIProvider(OpenAIProvider):
    """xAI (Grok) — uses OpenAI-compatible API at api.x.ai."""

    def __init__(self):
        super().__init__(
            base_url="https://api.x.ai/v1",
            api_key_env="XAI_API_KEY",
        )


# ── Gemini provider (via OpenAI-compatible endpoint) ─────────────

class GeminiProvider(OpenAIProvider):
    """Google Gemini — uses the OpenAI-compatible endpoint."""

    def __init__(self):
        super().__init__(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key_env="GEMINI_API_KEY",
        )


# ── Provider registry ────────────────────────────────────────────

_providers = {}

def get_provider(provider_name):
    """Get or create a provider instance by name.
    Providers are cached (one instance per provider type)."""
    if provider_name not in _providers:
        if provider_name == "anthropic":
            _providers[provider_name] = AnthropicProvider()
        elif provider_name == "openai":
            _providers[provider_name] = OpenAIProvider()
        elif provider_name == "xai":
            _providers[provider_name] = XAIProvider()
        elif provider_name == "gemini":
            _providers[provider_name] = GeminiProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}. Valid: anthropic, openai, xai, gemini")
    return _providers[provider_name]
