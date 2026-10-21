"""Run with `uv run python -m agrovision.assessments.worker`."""

import argparse
import json
import logging
import signal
import time

from agrovision.assessments.predictor import PredictorFailure, SupervisedPredictor
from agrovision.assessments.queue import Queue
from agrovision.config import get_settings
from agrovision.db import make_engine, make_sessions

logger = logging.getLogger("agrovision.worker")


class Worker:
    def __init__(self, settings):
        self.settings = settings
        self.engine = make_engine(settings.database_url)
        self.sessions = make_sessions(self.engine)
        self.queue = Queue(settings, self.sessions)
        self.predictor = SupervisedPredictor(settings)
        self.last_cleanup = 0.0

    def run_once(self):
        if time.monotonic() - self.last_cleanup >= 30:
            from agrovision.photos.cleanup import cleanup_once

            cleanup_once(self.settings, self.sessions)
            self.last_cleanup = time.monotonic()
        claim = self.queue.claim()
        if claim is None:
            return False
        logger.info(
            json.dumps({"event": "claimed", "assessment_id": claim.assessment_id, "attempt": claim.attempt})
        )
        try:
            result = self.predictor.run(claim)
            committed = self.queue.complete(claim, result)
            logger.info(
                json.dumps(
                    {
                        "event": "completed" if committed else "stale_lease",
                        "assessment_id": claim.assessment_id,
                    }
                )
            )
        except PredictorFailure as exc:
            self.queue.fail(claim, exc.code, exc.retryable)
            logger.warning(
                json.dumps(
                    {"event": "processing_error", "assessment_id": claim.assessment_id, "code": exc.code}
                )
            )
        except Exception:
            # Do not leak image data, paths, user notes or stack traces into logs/client results.
            self.queue.fail(claim, "model_execution_failed", True)
            logger.error(
                json.dumps(
                    {
                        "event": "processing_error",
                        "assessment_id": claim.assessment_id,
                        "code": "model_execution_failed",
                    }
                )
            )
        return True

    def close(self):
        self.predictor.close()
        self.engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    worker = Worker(get_settings())
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while running:
            worked = worker.run_once()
            if args.once:
                break
            if not worked:
                time.sleep(0.5)
    finally:
        worker.close()


if __name__ == "__main__":
    main()
