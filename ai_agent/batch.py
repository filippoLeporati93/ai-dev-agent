"""
batch.py
========
Anthropic Batch API helpers.

- batch_submit_and_poll: submit N requests, block until done, return Messages
- batch_loop: agentic loop driving one request per turn until no more tool_use
"""

import time

import anthropic

POLL_INTERVAL = 15
MAX_WAIT_SEC  = 3600


def batch_submit_and_poll(
    client: anthropic.Anthropic,
    requests: list[dict],
) -> dict[str, anthropic.types.Message]:
    """
    Submit a list of Batch API requests and block until all complete.
    Returns {custom_id: Message} for succeeded requests.
    Failed requests are logged and omitted — callers handle missing keys.
    """
    batch = client.messages.batches.create(requests=requests)
    print(f"  submitted batch {batch.id} ({len(requests)} requests)")

    waited = 0
    while waited < MAX_WAIT_SEC:
        batch  = client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts
        print(f"  {batch.processing_status} — "
              f"processing={counts.processing} "
              f"succeeded={counts.succeeded} "
              f"errored={counts.errored}")
        if batch.processing_status == "ended":
            break
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    else:
        raise TimeoutError(f"Batch {batch.id} did not complete within {MAX_WAIT_SEC}s")

    results: dict[str, anthropic.types.Message] = {}
    for result in client.messages.batches.results(batch.id):
        if result.result.type == "succeeded":
            results[result.custom_id] = result.result.message
        else:
            print(f"  warning: {result.custom_id} failed — {result.result}")
    return results


def batch_loop(
    client: anthropic.Anthropic,
    system: str,
    user: str,
    tools: list[dict],
    on_tool: callable,
    model: str,
    max_tokens: int = 8096,
) -> None:
    """
    Agentic loop: repeatedly call the Batch API, process tool calls, until
    Claude stops using tools or on_tool signals done.

    on_tool(name, input) must return (result_str, is_done: bool).
    When is_done is True the loop exits after processing all tools in that turn.
    """
    messages = [{"role": "user", "content": user}]
    turn = 1
    while True:
        print(f"\n  turn {turn}")
        results = batch_submit_and_poll(client, [{
            "custom_id": "req",
            "params": {
                "model":    model,
                "max_tokens": max_tokens,
                "system":   system,
                "tools":    tools,
                "messages": messages,
            },
        }])
        if "req" not in results:
            raise RuntimeError("Batch request failed — check logs above")

        response = results["req"]
        messages.append({"role": "assistant", "content": response.content})

        print(f"  stop_reason={response.stop_reason}  "
              f"usage=in:{response.usage.input_tokens} out:{response.usage.output_tokens}")

        if response.stop_reason != "tool_use":
            # Log any text Claude returned so we can diagnose silent failures
            for block in response.content:
                if hasattr(block, "text") and block.text.strip():
                    print(f"  [claude] {block.text.strip()[:500]}")
            break

        tool_results, stop = [], False
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"  [tool] {block.name}")
            result, done = on_tool(block.name, block.input)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     result,
            })
            if done:
                stop = True

        messages.append({"role": "user", "content": tool_results})
        if stop:
            break
        turn += 1