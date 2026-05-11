"""Summary abstraction only (no ``model`` / ``parse_match`` stack)."""

import logging

from legacy.mgz_legacy.summary.full import FullSummary

logger = logging.getLogger(__name__)


class SummaryStub:
    """``Summary`` callable: always uses full summary path (fast header + fast body with full fallback inside ``FullSummary``)."""

    def __call__(self, data, fallback=False):
        logger.info("using full summary")
        return FullSummary(data)


Summary = SummaryStub()
