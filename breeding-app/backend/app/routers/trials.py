"""试验与小区接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import MatingEvent, Trial, TrialPlot
from ..schemas import PlotCreate, TrialCreate

router = APIRouter(prefix="/api/trials", tags=["trials"])


def _plot_out(p: TrialPlot) -> dict:
    return {
        "id": p.id,
        "label": p.label,
        "replicate": p.replicate,
        "family_code": p.family.code if p.family else None,
    }


@router.get("")
def list_trials(session: Session = Depends(get_session)) -> list[dict]:
    trials = session.scalars(select(Trial).order_by(Trial.id)).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "season": t.season,
            "n_plots": len(t.plots),
        }
        for t in trials
    ]


@router.post("", status_code=201)
def create_trial(body: TrialCreate, session: Session = Depends(get_session)) -> dict:
    trial = Trial(name=body.name, season=body.season)
    session.add(trial)
    session.commit()
    return {"id": trial.id, "name": trial.name, "season": trial.season}


@router.post("/{trial_id}/plots", status_code=201)
def add_plot(
    trial_id: int, body: PlotCreate, session: Session = Depends(get_session)
) -> dict:
    trial = session.get(Trial, trial_id)
    if trial is None:
        raise HTTPException(404, f"试验 {trial_id} 不存在")
    family = None
    if body.family_code:
        family = session.scalars(
            select(MatingEvent).where(MatingEvent.code == body.family_code)
        ).first()
        if family is None:
            raise HTTPException(404, f"家系（交配事件）{body.family_code} 不存在")
    dup = session.scalars(
        select(TrialPlot).where(
            TrialPlot.trial_id == trial_id, TrialPlot.label == body.label
        )
    ).first()
    if dup is not None:
        raise HTTPException(422, f"小区 {body.label} 在该试验中已存在")
    plot = TrialPlot(
        trial_id=trial_id,
        label=body.label,
        replicate=body.replicate,
        family_id=family.id if family else None,
    )
    session.add(plot)
    session.commit()
    return _plot_out(plot)


@router.get("/{trial_id}/plots")
def list_plots(trial_id: int, session: Session = Depends(get_session)) -> list[dict]:
    trial = session.get(Trial, trial_id)
    if trial is None:
        raise HTTPException(404, f"试验 {trial_id} 不存在")
    plots = session.scalars(
        select(TrialPlot)
        .where(TrialPlot.trial_id == trial_id)
        .order_by(TrialPlot.replicate, TrialPlot.label)
    ).all()
    return [_plot_out(p) for p in plots]
