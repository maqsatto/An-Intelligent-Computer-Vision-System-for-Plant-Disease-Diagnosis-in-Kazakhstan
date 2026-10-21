"""Actual SIGKILL at durable boundaries, then recovery with a different process/token."""

import multiprocessing as mp

import pytest
from agrovision.models import Assessment, Job
from sqlalchemy import event, select
from test_worker import enqueue, expire

_RESULT = {
    "outcome": "inconclusive",
    "reason_codes": ["insufficient_evidence"],
    "prediction": None,
    "candidates": [],
    "quality": {"status": "not_assessed", "flags": []},
    "next_action": "consult_expert",
}


def _interrupted_worker(settings, boundary, connection):
    from agrovision.assessments.worker import Worker

    worker = Worker(settings)
    claim = worker.queue.claim()
    if boundary == "before_commit":
        # Use actual Queue.complete; stop after SQL writes flush, before its transaction commits.
        def hold_before_commit(session):
            session.flush()
            connection.send(claim)
            connection.recv()

        event.listen(worker.sessions.class_, "before_commit", hold_before_commit)
        worker.queue.complete(claim, _RESULT)
    elif boundary == "after_commit":
        assert worker.queue.complete(claim, _RESULT)
        connection.send(claim)
        connection.recv()
    else:
        connection.send(claim)
        connection.recv()


@pytest.mark.parametrize("boundary", ["after_claim", "before_commit", "after_commit"])
def test_sigkill_restart_has_one_committed_result(client, headers, settings, app, worker, boundary):
    assessment_id = enqueue(client, headers)
    context = mp.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_interrupted_worker, args=(settings, boundary, child))
    process.start()
    child.close()
    try:
        assert parent.poll(15), "worker did not reach controlled boundary"
        old = parent.recv()
        assert old.assessment_id == assessment_id
        process.kill()  # Actual SIGKILL, no graceful cleanup/rollback code in child.
        process.join(timeout=5)
        assert not process.is_alive()
        with app.state.sessions() as db:
            current = db.get(Assessment, assessment_id)
            if boundary == "after_commit":
                assert current.status == "completed"
                assert current.result == _RESULT
            else:
                assert current.status == "running" and current.result is None
        if boundary == "after_commit":
            assert not worker.run_once()
        else:
            expire(app, old.job_id)
            assert worker.run_once()
        with app.state.sessions() as db:
            final = db.get(Assessment, assessment_id)
            assert final.status == "completed"
            assert final.result["outcome"] == "inconclusive"
            assert db.scalar(select(Job).where(Job.assessment_id == assessment_id)).attempts == (
                1 if boundary == "after_commit" else 2
            )
        assert not worker.queue.complete(old, _RESULT)
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        parent.close()
