"""
batch.py
========
Anthropic Batch API.

Public API
----------
  batch_single           — one request → text (select/plan steps)
  batch_submit_and_poll  — N parallel requests → {id: Message} (write step)
  batch_loop             — multi-turn agentic loop (reserved for future use)
"""

import time
from typing import Callable

import anthropic

from ai_agent.config import POLL_INTERVAL_SEC, MAX_WAIT_SEC
from ai_agent.errors import BatchError


def batch_submit_and_poll(
    client: anthropic.Anthropic,
    requests: list[dict],
) -> dict[str, anthropic.types.Message]:
    """
    Submit a list of Batch API requests and block until all complete.
    Returns {custom_id: Message} for succeeded requests.
    Failed requests are logged and omitted — callers handle missing keys.
    """
    if not requests:
        return {}

    batch = client.messages.batches.create(requests=requests)
    print(f"  submitted batch {batch.id} ({len(requests)} requests)")

    waited = 0
    while waited < MAX_WAIT_SEC:
        batch = client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts
        print(
            f"  {batch.processing_status} — "
            f"processing={counts.processing} "
            f"succeeded={counts.succeeded} "
            f"errored={counts.errored}"
        )
        if batch.processing_status == "ended":
            break
        time.sleep(POLL_INTERVAL_SEC)
        waited += POLL_INTERVAL_SEC
    else:
        raise BatchError(
            f"Batch {batch.id} did not complete within {MAX_WAIT_SEC}s"
        )

    results: dict[str, anthropic.types.Message] = {}
    for result in client.messages.batches.results(batch.id):
        if result.result.type == "succeeded":
            results[result.custom_id] = result.result.message
        else:
            print(f"  warning: {result.custom_id} failed — {result.result}")
    return results


def batch_single(
    client: anthropic.Anthropic,
    system: str,
    user: str,
    model: str,
    max_tokens: int = 8_000,
) -> str:
    """
    Submit one request via the Batch API, return the text response.
    Workhorse for select/plan steps that need a single JSON answer.
    """
    results = batch_submit_and_poll(client, [{
        "custom_id": "req",
        "params": {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
    }])

    if "req" not in results:
        raise BatchError("Single batch request failed — check logs above")

    msg = results["req"]
    print(f"  usage=in:{msg.usage.input_tokens} out:{msg.usage.output_tokens}")
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def batch_loop(
    client: anthropic.Anthropic,
    system: str,
    user: str,
    tools: list[dict],
    on_tool: Callable[[str, dict], tuple[str, bool]],
    model: str,
    max_tokens: int = 8_000,
) -> None:
    """
    Multi-turn agentic loop with tool_use handling.
    Reserved for future modes that need multi-step reasoning.
    """
    messages: list[dict] = [{"role": "user", "content": user}]
    turn = 1

    while True:
        print(f"\n  turn {turn}")
        results = batch_submit_and_poll(client, [{
            "custom_id": "req",
            "params": {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "tools": tools,
                "messages": messages,
            },
        }])

        if "req" not in results:
            raise BatchError("Batch request failed — check logs above")

        response = results["req"]
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results, stop = [], False
        for block in response.content:
            if block.type != "tool_use":
                continue
            result, done = on_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })
            if done:
                stop = True

        messages.append({"role": "user", "content": tool_results})
        if stop:
            break
        turn += 1