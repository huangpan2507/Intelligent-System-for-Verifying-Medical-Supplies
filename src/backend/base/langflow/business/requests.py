"""Durable call receipts. A local id is correlation, never a promise of remote idempotency."""

import httpx

from langflow.business.datasets import safe_json
from langflow.business.models import ExternalRequest
from langflow.verification.database import now


class AcceptedResponseError(ValueError):
    """The provider acknowledged work but did not return a synchronous result."""

    def __init__(self, response):
        super().__init__("Remote work accepted; completion is unconfirmed")
        self.response = response


class UnreadableResponseError(ValueError):
    """Preserve the received body even when the declared JSON protocol cannot parse it."""

    def __init__(self, response):
        super().__init__("Response is not valid JSON")
        self.response = response


def prepare(store, node, source, row_id, connection, payload):
    with store.database.sessions.begin() as session:
        receipt = ExternalRequest(
            task_id=store.task_id,
            node_id=node,
            input_dataset_id=source["id"],
            input_row_id=row_id,
            connection_id=connection.id,
            payload=safe_json(payload),
        )
        session.add(receipt)
        session.flush()
        return receipt.id


def update(store, request_id, **values):
    with store.database.sessions.begin() as session:
        receipt = session.get(ExternalRequest, request_id)
        if receipt.task_id != store.task_id:
            msg = "Request does not belong to this task"
            raise ValueError(msg)
        for key, value in values.items():
            setattr(receipt, key, value)


def call(store, request_id, send):
    # This second commit is also before the network call. If it fails, do not send.
    update(store, request_id, transport="attempted")
    try:
        response = send()
    except AcceptedResponseError as exc:
        update(
            store,
            request_id,
            transport="responded",
            remote="accepted",
            response=safe_json(exc.response),
            error="completion_unconfirmed",
            finished_at=now(),
        )
        raise
    except UnreadableResponseError as exc:
        update(
            store,
            request_id,
            transport="response_unreadable",
            remote="unknown",
            response=exc.response,
            error="invalid_json",
            finished_at=now(),
        )
        raise
    except httpx.HTTPStatusError as exc:
        # An HTTP status alone does not prove a synchronous job was not accepted.
        update(
            store,
            request_id,
            transport="http_error",
            remote="unknown",
            error=f"HTTP {exc.response.status_code}",
            finished_at=now(),
        )
        raise
    except httpx.HTTPError as exc:
        update(
            store,
            request_id,
            transport="transport_error",
            remote="unknown",
            error=type(exc).__name__,
            finished_at=now(),
        )
        raise
    except (ValueError, TypeError) as exc:
        update(
            store,
            request_id,
            transport="response_unreadable",
            remote="unknown",
            error=type(exc).__name__,
            finished_at=now(),
        )
        raise
    update(
        store, request_id, transport="responded", remote="completed", response=safe_json(response), finished_at=now()
    )
    return response
