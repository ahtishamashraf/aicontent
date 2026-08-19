"""Shared fixtures."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from detection.engines.fake import FakeProvider


@pytest.fixture
def settings() -> Settings:
    """Default development settings, isolated from any .env file."""
    return Settings(_env_file=None)


@pytest.fixture
def provider() -> FakeProvider:
    p = FakeProvider()
    p.load()
    return p


@pytest.fixture
def english_text() -> str:
    """~200 words of ordinary English prose with varied structure."""
    return (
        "The committee reviewed the revised proposal during the March session, and "
        "several members raised concerns about the delivery timeline. In particular, "
        "the assumption that procurement would complete before the summer recess "
        "struck two of them as optimistic. The chair agreed to circulate a revised "
        "schedule before the next meeting.\n\n"
        "A second matter concerned staffing levels across the department. Two "
        "vacancies have gone unfilled since January, and the resulting workload has "
        "fallen on a team smaller than the original plan assumed. Recruitment is "
        "under way, but suitable candidates remain scarce in this specialism, and "
        "the salary band has not moved in three years.\n\n"
        "Finally, the group discussed the archive migration. Progress has been slow "
        "because the source records are inconsistent: some are catalogued by "
        "accession number, others by donor, and a handful by nothing at all. The "
        "archivist proposed a triage approach, tackling the catalogued material "
        "first and setting aside the remainder for a later phase. Nobody objected, "
        "though one member noted that later phases have a habit of never arriving."
    )
