"""Web adapter for Tejido — FastAPI app + (eventually) React frontend.

Adapters translate transport primitives into calls into the
transport-neutral controller in `circle.controller.*`. This module is the
HTTP/SSE side of that translation.

For now (commit 2 of the web buildout) only the join + state endpoints
exist; SSE streaming, message submission, and callback dispatch arrive in
later commits, all building on the same controller.
"""
