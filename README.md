# 🍕 LangSlice Pizza Agent

The course repo for **LangSmith Essentials**. LangSlice is a fictional pizzeria, and
this agent answers questions about the shop and takes pizza orders. Every run traces to
LangSmith.

The agent ships with two deliberate bugs. Finding them in the traces is the exercise.

## Repo layout

```text
lca-langsmith-essentials/
├── .env.example                # env template: copy to .env and add your keys
├── env_utils.py                # setup checker, invoked by each project's check_setup.py
├── BUGS.md                     # what the two bugs are (spoilers)
├── langgraph-agent/            # the main agent, the one the lessons follow
│   ├── agent.py                # system prompt, the nine tools, the create_agent call
│   ├── database.py             # knowledge base, ingredient catalog, menu, live orders
│   ├── langgraph.json          # points Studio at the agent and serves the chat UI
│   ├── run_agent.py            # terminal chat
│   ├── eval.py                 # runs the agent over a dataset (Module 2)
│   ├── stock_evaluator.py      # the Module 2 evaluator
│   ├── check_setup.py          # runs the root setup checker against this project
│   ├── ui/                     # customer chat UI, served on port 2024
│   └── traces/                 # recorded conversations, plus upload and download scripts
└── claude-sdk-agent/           # the same pizzeria on the Claude Agent SDK, same filenames
```

Each agent folder keeps its own `pyproject.toml`, `uv.lock`, and `.venv`. There is nothing to
install at the repo root.

## Two implementations

| Project | Harness | Model | Interfaces |
| --- | --- | --- | --- |
| `langgraph-agent/` | LangChain `create_agent` + LangGraph | `openai:gpt-5-nano` | Studio, chat UI, terminal |
| `claude-sdk-agent/` | Claude Agent SDK | `claude-opus-5` | terminal |

Same system prompt, same nine tools, same database, same two bugs. The lessons follow
`langgraph-agent/`, so every command below runs from in there unless it says otherwise.

`claude-sdk-agent/` has no LangChain and no LangGraph installed. Its agent loop runs
inside a `claude` CLI subprocess and reports nothing on its own, so `agent.py` turns
tracing on with a single call to `configure_claude_agent_sdk()`, following
[the LangSmith integration docs](https://docs.langchain.com/langsmith/trace-claude-agent-sdk).
Both projects send traces to the same project in the same shape, tagged with `harness`
metadata. Span names differ slightly between the two: on the Claude SDK side, model
calls appear as `claude.assistant.turn` and tools carry their MCP prefix, as in
`mcp__pizzeria__add_pizza_to_order`.

## Setup

```bash
cp .env.example .env      # then choose the credentials for your harness below
```

`.env` lives at the repo root and both agent folders read it.

### Choose local chat authentication

- **Direct provider (default):** `langgraph-agent/` uses `OPENAI_API_KEY` for its default OpenAI model
- **LangSmith LLM Gateway:** for `langgraph-agent/`, set `LANGSMITH_GATEWAY=true` and `LANGSMITH_API_KEY`. Your workspace administrator must configure the OpenAI provider secret and grant model access. You can leave `OPENAI_API_KEY` unset locally
- **Claude Agent SDK:** `claude-sdk-agent/` still needs its own `claude` CLI login or `ANTHROPIC_API_KEY`. `LANGSMITH_GATEWAY` configures LangChain integrations, not this harness

For a separate gateway credential, set `LANGSMITH_GATEWAY_API_KEY`; it overrides `LANGSMITH_API_KEY` for gateway chat only. Tracing and the LangSmith dataset and evaluation APIs still need `LANGSMITH_API_KEY`. Turning tracing off does not disable gateway chat, and a gateway-only key does not enable tracing.

For another region, set `LANGSMITH_GATEWAY` to a gateway base URL such as `https://eu.gateway.smith.langchain.com`, `https://apac.gateway.smith.langchain.com`, or `https://aws.gateway.smith.langchain.com`. The integration appends `/openai/v1`; do not include it yourself. `LANGSMITH_ENDPOINT` selects the tracing/API region separately. Unset provider base URL overrides to use automatic gateway routing. See [direct model access](https://docs.langchain.com/langsmith/llm-gateway-direct-model-access).

Unset `LANGSMITH_GATEWAY`, or set it to `false`, `0`, `no`, or an empty value, to return to direct provider access. You can export these variables in your shell without creating `.env`. If `.env` exists, this repository loads it with `override=True`, so file values win over shell values. Restart running agents after changes.

### Install and check

Each project has its own `pyproject.toml`, `uv.lock`, and `.venv`. Set up the one you
plan to use:

```bash
cd langgraph-agent        # or claude-sdk-agent
uv sync
uv run python check_setup.py
```

`check_setup.py` reports whether your keys load, then checks the packages for whichever
project you ran it from. There is nothing to install at the repo root.

The checker reports missing, empty, and placeholder credentials for the selected harness and mode. It checks presence, not whether a key is valid. After `uv sync`, you can verify gateway chat with no local provider keys from `langgraph-agent/`:

```bash
uv run python run_agent.py -m "What pizzas do you have?"
```

With `LANGSMITH_GATEWAY=true` and a working gateway key, the agent replies without `OPENAI_API_KEY`. Authentication or access errors still need a valid key for the right region, a workspace provider secret, and permission to use the selected model.

### Configure server-side evaluations

Later in the course, LangSmith calls a model itself. So `OPENAI_API_KEY` also needs to be
a workspace secret in LangSmith, under **Settings → Provider secrets**. This is the one
provider secret both harnesses need, and the Module 4 judge prompt is calibrated against
an OpenAI model, so put an OpenAI key here even if you only ever run `claude-sdk-agent/`.

`claude-sdk-agent/` needs no OpenAI key in `.env`, and usually no Anthropic key either.
It reuses an existing `claude` CLI login, so run `claude` once to log in, or set
`ANTHROPIC_API_KEY`. The workspace secret above is a separate requirement and still
applies, whichever harness you run, because LangSmith calls the model from its own
servers rather than from your machine.

## Running the agent

LangGraph Studio gives you the graph view, checkpoints, interrupts, and forking:

```bash
uv run langgraph dev
```

Studio opens against the local server on port 2024, aimed at `agent.py:pizza_agent` by
`langgraph.json`. The customer chat UI is served from the same port at
`http://127.0.0.1:2024/`, and its transcript shows prose only, leaving tool calls to
Studio and LangSmith. On Safari, run `uv run langgraph dev --tunnel`.

Terminal chat:

```bash
uv run run_agent.py
uv run run_agent.py --show-tools               # print every tool call and result
uv run run_agent.py -m "how late are you open on friday?"
```

`claude-sdk-agent/` has no graph, so it has no Studio and no chat UI. The same three
commands work there, and `--show-tools` also prints token counts and cost.

This message is an example input that reaches many  of the tools in a single turn, which is handy in Studio:

> Hey this is Paul, I want a large hand tossed pizza with pepperoni and pineapple for
> pickup, no special instructions.

Orders live in `database.ORDERS`, keyed by `thread_id`, while graph state holds only
`messages`. Forking does not roll an order back, so re-running from the first message
adds a second pizza to an order that already exists.

## Recorded traces

`traces/` holds conversations captured from this same agent, which lets you read a
spread of orders without generating them. It is its own small uv project:

```bash
cd traces
uv sync
uv run python upload_traces.py --input traces-1.json     # Module 1
uv run python upload_traces.py --input traces-2.json     # Module 4
```

`download_traces.py` pulls traces back out of a project.

## Evaluation

`eval.py` replays each example from the dataset named in `DATASET_NAME` on a fresh
`thread_id`, then scores the result with `stock_evaluator.py`:

```bash
uv run python eval.py
```

`stock_evaluator.py` reads plain dictionaries, so one evaluator scores both harnesses.
It is a byte-identical copy in each project, as is `database.py`. Keep them that way.

## Deployment

Module 3 deploys the LangGraph agent:

```bash
uv run langgraph deploy --name langslice-deployment
```

## The two bugs

The first bug shows up in a Module 1 trace and gets fixed in Module 2. The second stays
hidden until Module 4, when live traffic brings it out. `BUGS.md` describes both, so
skip that file if you are doing the exercise and want to avoid spoilers.

Note: Each project holds its own copy of the agent and the database, so an edit that fixes a
bug in one leaves the other untouched.

## Tools

| Tool | Purpose |
| --- | --- |
| `search_company_info` | Keyword search over the company knowledge base |
| `get_menu` | Sizes, crusts, specialty pizzas, toppings, sides |
| `start_order` | Open an order for pickup or delivery |
| `add_pizza_to_order` | Validate and add a pizza |
| `modify_pizza` | Change a pizza already on the order |
| `remove_pizza` | Drop a pizza |
| `add_side` | Add a side or a drink |
| `view_order` | Current line items and totals |
| `confirm_order` | Price the order and send it to the kitchen |

## Configuration

Shared, in the root `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LANGSMITH_TRACING` | true | Set `true` to turn tracing on |
| `LANGSMITH_API_KEY` | none | Required for tracing and LangSmith API operations; fallback gateway credential |
| `LANGSMITH_GATEWAY` | unset | Enable LangChain gateway chat with `true` or a regional gateway base URL |
| `LANGSMITH_GATEWAY_API_KEY` | unset | Optional gateway-only key override; not a tracing key |
| `LANGSMITH_PROJECT` | `langslice-pizza-agent` | Project the traces land in |
| `LANGSMITH_ENDPOINT` | US | Uncomment your region's endpoint outside the US |
| `DATASET_NAME` | `langslice-dataset` | Dataset used by `eval.py` |

`langgraph-agent/`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Required for direct local OpenAI chat, not gateway chat |
| `PIZZA_AGENT_MODEL` | `openai:gpt-5-nano` | Model id, passed to `init_chat_model` |
| `PIZZA_AGENT_REASONING_EFFORT` | `low` | Applies to gpt-5 models. Leave empty to unset |

`claude-sdk-agent/`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | unset | Optional, a `claude` CLI login is used if present |
| `PIZZA_AGENT_CLAUDE_MODEL` | `claude-opus-5` | Model id |
| `PIZZA_AGENT_CLAUDE_EFFORT` | `low` | `low` \| `medium` \| `high` \| `xhigh` \| `max` |
| `EVAL_CONCURRENCY` | `2` | Parallel examples in `eval.py`, each a CLI subprocess |

## The sentiment evaluator (Module 4)

Module 4 builds an LLM-as-a-judge evaluator for customer sentiment. It lives in the
LangSmith UI rather than in this repo, and it is unrelated to `stock_evaluator.py`,
which is the Module 2 offline evaluator.

It runs on threads rather than on individual traces, so one score covers a whole
conversation. These settings are the same for both versions of the prompt:

| Field | Value |
| --- | --- |
| Variable | `{{{human_ai_pairs}}}`, bound to the thread's `human_ai_pairs` field |
| Feedback key | `sentiment` |
| Description | `Customer sentiment score as 1 (clearly positive) or 0 (negative)` |
| Type | Boolean |
| Sampling | 100%, source `Threads`, thread idle time 2 minutes |

### Version 1, tone only (4.1)

```
You are an expert customer-experience evaluator assessing customer sentiment across multi-turn conversations with a pizza-ordering agent.

<Rubric>
Score 0 for negative sentiment when the customer's own language is negative:
- The customer expresses disbelief, annoyance, impatience, or anger ("what??", "that can't be right", "are you kidding me").
- The customer raises their voice - capitals, repeated punctuation, or repeated objections.
- The customer insults or mocks the shop, or is sarcastic about it.
- The customer threatens to leave a review, tell other people, or take their business elsewhere.
- The customer signs off dismissively ("forget it", "I'm done", "I'll leave it").
- The emotional temperature of the customer's messages rises as the conversation continues.

Score 1 for positive sentiment when the customer's language stays pleasant, calm, or matter-of-fact:
- The customer is polite or friendly, or thanks the agent.
- The customer is brief, plain, or agreeable, with none of the negative markers above.
- The customer disagrees with or corrects the agent in plain, unemotional terms ("that's not right", "no") - disagreement is not the same as displeasure.
- The customer goes along with what the agent suggests.
</Rubric>

<Instructions>
- Read the entire conversation.
- Evaluate the customer's sentiment, not the agent's tone.
- Judge the feeling the customer expresses, not whether the order was completed - task success is tracked separately.
- Pay particular attention to how the emotional temperature changes across turns.
- Treat tool messages as context for understanding what caused the customer's reaction.
- Do not give a positive score merely because the agent remains polite.
- Select the score that best represents the customer's expressed sentiment, giving extra weight to their language near the end of the conversation.
- Briefly explain the score using specific evidence from the customer's messages.
</Instructions>

<Reminder>
- The most important signal is the words the customer chooses.
- Escalating phrases such as "what?", "are you kidding me?", or repeated objections indicate increasingly negative sentiment.
- Sarcasm counts as negative even though the individual words are positive.
- A polite agent response does not cancel out customer frustration.
- Absence of negative language is positive sentiment.
</Reminder>

  <conversation>
  {{{human_ai_pairs}}}
  </conversation>
```

### Version 2, tone and outcome (4.2)

Reviewing the judge's scores by hand in an annotation queue turns up two false
positives. Version 1's rubric only describes what frustration sounds like, so a
customer who stays calm and still leaves without what they came for gets waved through.
Version 2 adds an outcome section, and makes a positive score require both a pleasant
tone and a resolved request:

```
You are an expert customer-experience evaluator assessing customer sentiment across multi-turn conversations with a pizza-ordering agent.

<Rubric>
Score 0 for negative sentiment when the customer's own language is negative:
- The customer expresses disbelief, annoyance, impatience, or anger ("what??", "that can't be right", "are you kidding me").
- The customer raises their voice - capitals, repeated punctuation, or repeated objections.
- The customer insults or mocks the shop, or is sarcastic about it.
- The customer threatens to leave a review, tell other people, or take their business elsewhere.
- The customer signs off dismissively ("forget it", "I'm done", "I'll leave it").
- The emotional temperature of the customer's messages rises as the conversation continues.

Also score 0 on outcome, whatever the tone:
- The customer's problem remains unresolved at the end of the conversation.
- The agent asks the customer to accept an unreasonable workaround, or to buy something they did not want, in order to get what they asked for.
- The customer gives up on their original request, or settles for something lesser than what they came for.

Score 1 for positive sentiment only when the customer's language stays pleasant, calm, or matter-of-fact AND they got what they came for:
- The customer is polite or friendly, or thanks the agent.
- The customer is brief, plain, or agreeable, with none of the negative markers above.
- The customer goes along with what the agent suggests.

Do not score 0 merely because:
- The agent uses tools or asks necessary clarification questions.
- The customer uses brief or informal language without showing frustration.

Flat affect is not a positive score. A customer who writes only "that's not right." and "no. just the pizzas." and leaves without an order scores 0 - brevity with an unresolved order is still a bad experience. A customer who stays cheerful, complies with an upsell, is refused a second time, and signs off with "thanks anyway" scores 0 for the same reason.
</Rubric>

<Instructions>
- Read the entire conversation.
- Evaluate the customer's sentiment, not the agent's tone.
- Consider whether the customer's request was successfully resolved. An unresolved order is a bad experience however politely it ends.
- Pay particular attention to how sentiment changes across turns.
- Treat tool messages as context for understanding what caused the customer's reaction.
- Do not give a positive score merely because the agent remains polite.
- Select the score that best represents the customer's overall experience, giving extra weight to their sentiment near the end of the conversation.
- Briefly explain the score using specific evidence from the customer's messages.
</Instructions>

<Reminder>
- The most important signal is the customer's language throughout the full conversation.
- Escalating phrases such as "what?", "are you kidding me?", or repeated objections indicate increasingly negative sentiment.
- Sarcasm counts as negative even though the individual words are positive.
- A polite agent response does not cancel out customer frustration.
- Absence of negative language is not evidence of a good experience.
</Reminder>

  <conversation>
  {{{human_ai_pairs}}}
  </conversation>
```

What changed between the two:

| Version 1 | Version 2 |
| --- | --- |
| Tone only, with task success tracked separately | Adds an outcome block that scores `0` regardless of tone |
| Score `1` when the language is pleasant, calm, or matter-of-fact | Score `1` only when the language is pleasant and the request was resolved |
| "Absence of negative language is positive sentiment" | "Absence of negative language is not evidence of a good experience" |
| Plain disagreement counts as positive | Flat affect with an unresolved order counts as negative |
