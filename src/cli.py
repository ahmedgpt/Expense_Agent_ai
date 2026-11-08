"""Interactive command-line chat interface."""

from __future__ import annotations

import argparse
import asyncio

from src.agent import AgentInvocationError, create_expense_agent


async def chat(user_id: str, session_id: str, verbose: bool) -> None:
    try:
        agent = await create_expense_agent(user_id=user_id, verbose=verbose)
    except (RuntimeError, OSError) as exc:
        print(f"Could not start the agent: {exc}")
        return
    thread_id = f"{user_id}:{session_id}"
    print("Expense assistant ready. Type 'exit' or 'quit' to leave.")
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.casefold() in {"exit", "quit"}:
            return
        try:
            result = await agent.ainvoke(text, thread_id)
        except AgentInvocationError as exc:
            print(f"Assistant: I couldn't complete that request after retrying. {exc}")
            continue
        print(f"Assistant: {result['answer']}")
        if verbose:
            for call in result["tools"]:
                print(f"Tool used: {call['name']} args={call.get('args', {})}")
                if "result" in call:
                    print(f"  Result: {call['result']}")
            for retrieval in result["retrieved_chunks"]:
                print(f"Retrieved chunk ({retrieval['name']}): {retrieval['result']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal Expense Management Agent")
    parser.add_argument("--user", required=True, help="User identifier for scoped memory")
    parser.add_argument("--session", required=True, help="Conversation session identifier")
    parser.add_argument("--verbose", action="store_true", help="Print tool calls and retrieved evidence")
    args = parser.parse_args()
    asyncio.run(chat(args.user, args.session, args.verbose))


if __name__ == "__main__":
    main()
