"""Transport-neutral controller — drives the conversation state machine.

Adapters (Telegram, web) translate transport primitives (Telegram updates,
HTTP requests) into calls into this layer and render its yielded
`OutboundAction`s back into the transport's primitives.

Each controller module exposes async-generator functions that yield
actions as work progresses. Locks are held only across state mutations
(load → mutate → save) and never across yields, so the consumer can
render an intermediate action while the controller waits on the next
LLM call.
"""
