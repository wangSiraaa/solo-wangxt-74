"""家系统计接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import TraitObservation, TrialPlot
from ..stats import family_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/trial/{trial_id}/traits")
def trial_traits(trial_id: int, session: Session = Depends(get_session)) -> list[str]:
    rows = session.scalars(
        select(TraitObservation.trait)
        .join(TrialPlot, TraitObservation.plot_id == TrialPlot.id)
        .where(TrialPlot.trial_id == trial_id)
        .distinct()
    ).all()
    return sorted(rows)


@router.get("/trial/{trial_id}/families")
def trial_family_stats(
    trial_id: int, trait: str, session: Session = Depends(get_session)
) -> dict:
    try:
        return family_stats(session, trial_id, trait)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
