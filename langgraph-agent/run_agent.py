"""Run the LangSlice pizza agent from the terminal.

Interactive chat:

    uv run run_agent.py

One-shot message:

    uv run run_agent.py -m "what time do you close on friday?"

Flags:
    --show-tools   print every tool call and result as it happens
    --thread ID    reuse a specific conversation/order id
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

from dotenv import load_dotenv
from langchain.messages import AIMessage, HumanMessage, ToolMessage

import database as db
from agent import GREETING, MODEL_NAME, pizza_agent

# override=True so .env always wins over pre-existing OS environment
# variables, which keeps a student's shell from silently shadowing their .env.
load_dotenv(override=True)


def _print_tool_traffic(messages: list) -> None:
    """Pretty-print tool calls and tool results from a turn's new messages."""
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                args = json.dumps(call["args"], ensure_ascii=False)
                print(f"  \033[36m-> {call['name']}({args})\033[0m")
        elif isinstance(message, ToolMessage):
            content = str(message.content)
            if len(content) > 700:
                content = content[:700] + " ...[truncated]"
            print(f"  \033[90m<- {message.name}: {content}\033[0m")


def _final_text(message: AIMessage) -> str:
    """Extract plain text from an assistant message (content may be blocks)."""
    content = message.content
    if isinstance(content, str):
        return content
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p).strip()


def _terminal_text(message: AIMessage) -> str:
    """Adapt rich assistant output for a terminal without changing the agent."""
    text = _final_text(message)
    if "## 🍕 LangSlice Menu" in text:
        return db.format_menu_terminal()
    return text


def send(history: list, text: str, thread_id: str, show_tools: bool) -> list:
    """Send one customer message through the agent and print the reply."""
    history = [*history, HumanMessage(content=text)]
    show_thinking = sys.stdout.isatty()
    if show_thinking:
        print("\033[1mSal:\033[0m Thinking...", end="", flush=True)
    try:
        result = pizza_agent.invoke(
            {"messages": history},
            config={"configurable": {"thread_id": thread_id}},
        )
    finally:
        if show_thinking:
            # Return to the start and erase the placeholder before printing the
            # tool traffic or final response in its place.
            print("\r\033[2K", end="", flush=True)
    messages = result["messages"]

    if show_tools:
        _print_tool_traffic(messages[len(history) :])

    print(f"\033[1mSal:\033[0m {_terminal_text(messages[-1])}\n")
    return messages


def print_order(thread_id: str) -> None:
    """Print a readable receipt for the order this conversation built."""
    order = db.get_order(thread_id)
    if order is None:
        print("(no order was started)")
        return
    summary = db.order_summary(order)
    print(f"\n\033[1mOrder #{summary['order_id']}\033[0m")
    print("=" * (7 + len(summary["order_id"])))
    print(f"Customer: {summary['customer_name']}")
    print(f"Type:     {summary['order_type'].title()}")
    print(f"Status:   {summary['status'].title()}")
    if summary["address"]:
        print(f"Address:  {summary['address']}")

    if summary["pizzas"]:
        print("\n\033[1mPizzas\033[0m")
        for pizza in summary["pizzas"]:
            print(
                f"  #{pizza['pizza_number']}  {pizza['quantity']}x "
                f"{pizza['size'].title()} {pizza['crust'].title()}"
                f"  ${pizza['line_total']:.2f}"
            )
            toppings = ", ".join(name.title() for name in pizza["toppings"])
            print(f"      {toppings or 'No toppings'}")
            if pizza["notes"]:
                print(f"      Note: {pizza['notes']}")

    if summary["sides"]:
        print("\n\033[1mSides & Drinks\033[0m")
        for side in summary["sides"]:
            print(
                f"  {side['quantity']}x {side['item'].title()}"
                f"  ${side['line_total']:.2f}"
            )

    if not summary["pizzas"] and not summary["sides"]:
        print("\n  (order is empty)")

    print("\n\033[1mTotals\033[0m")
    print(f"  Subtotal       ${summary['subtotal']:.2f}")
    if summary["order_type"] == "delivery":
        print(f"  Delivery fee   ${summary['delivery_fee']:.2f}")
    print(f"  Tax            ${summary['tax']:.2f}")
    print(f"  \033[1mTotal          ${summary['total']:.2f}\033[0m\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat with the LangSlice pizza agent.")
    parser.add_argument("-m", "--message", help="send a single message and exit")
    parser.add_argument(
        "--show-tools", action="store_true", help="print tool calls and results"
    )
    parser.add_argument("--thread", help="conversation id (defaults to a fresh uuid)")
    args = parser.parse_args()

    thread_id = args.thread or str(uuid.uuid4())
    tracing = os.getenv("LANGSMITH_TRACING", "").lower() in {"1", "true", "yes"}

    print(f"\033[1mLangSlice\033[0m - model {MODEL_NAME}, thread {thread_id}")
    if tracing:
        print(f"tracing to LangSmith project: {os.getenv('LANGSMITH_PROJECT', 'default')}")
    print()

    # Sal opens the conversation, so every mode starts from the same footing the
    # customer sees in the UI.
    history: list = [AIMessage(content=GREETING)]
    print(f"\033[1mSal:\033[0m {GREETING}\n")

    if args.message:
        send(history, args.message, thread_id, args.show_tools)
        return 0

    print("Type your message, or 'order' to view the current order, 'quit' to exit.\n")
    while True:
        try:
            text = input("\033[1mYou:\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in {"quit", "exit", "q"}:
            break
        if text.lower() == "order":
            print_order(thread_id)
            continue
        history = send(history, text, thread_id, args.show_tools)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
