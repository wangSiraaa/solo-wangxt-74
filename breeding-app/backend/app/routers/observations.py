"""性状观测接口：录入、补录、按小区查询。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import (
    Germplasm,
    ObsStatus,
    TraitObservation,
    TrialPlot,
)
from ..schemas import ObservationCreate, ObservationUpdate

router = APIRouter(prefix="/api/observations", tags=["observations"])


def _out(o: TraitObservation) -> dict:
    return {
        "id": o.id,
        "plot_id": o.plot_id,
        "plot_label": o.plot.label,
        "plant_tag": o.plant_tag,
        "germplasm_code": o.germplasm.code if o.germplasm else None,
        "trait": o.trait,
        "status": o.status.value,
        "value": o.value,
        "observed_on": o.observed_on.isoformat(),
        "source": o.source,
        "backfilled": o.backfilled,
        "created_at": o.created_at.isoformat(),
        "updated_at": o.updated_at.isoformat(),
    }


@router.post("", status_code=201)
def create_observation(
    body: ObservationCreate, session: Session = Depends(get_session)
) -> dict:
    plot = session.get(TrialPlot, body.plot_id)
    if plot is None:
        raise HTTPException(404, f"小区 {body.plot_id} 不存在")
    germplasm = None
    if body.germplasm_code:
        germplasm = session.scalars(
            select(Germplasm).where(Germplasm.code == body.germplasm_code)
        ).first()
        if germplasm is None:
            raise HTTPException(
                404,
                f"材料 {body.germplasm_code} 不存在；标签丢失时请留空，不要猜测归属",
            )
    obs = TraitObservation(
        plot_id=plot.id,
        plant_tag=body.plant_tag,
        germplasm_id=germplasm.id if germplasm else None,
        trait=body.trait,
        status=body.status,
        value=body.value,
        observed_on=body.observed_on or date.today(),
        source=body.source,
    )
    session.add(obs)
    session.commit()
    return _out(obs)


@router.patch("/{obs_id}")
def update_observation(
    obs_id: int, body: ObservationUpdate, session: Session = Depends(get_session)
) -> dict:
    """补录/更正观测，全部留痕（source 必填，updated_at 自动更新）。"""
    obs = session.get(TraitObservation, obs_id)
    if obs is None:
        raise HTTPException(404, f"观测 {obs_id} 不存在")

    old, new = obs.status, body.status
    if old == ObsStatus.DEAD and new == ObsStatus.MEASURED:
        raise HTTPException(422, "死亡植株不能再补测定值；请保持死亡状态")
    if old == ObsStatus.MEASURED and new in (ObsStatus.MISSING, ObsStatus.DEAD):
        raise HTTPException(422, "已测记录不能改回未测/死亡；如录入错误请更正数值并注明来源")
    if old == ObsStatus.MISSING and new == ObsStatus.MISSING:
        raise HTTPException(422, "记录已是未测状态，无需补录")

    if old == ObsStatus.MISSING and new == ObsStatus.MEASURED:
        obs.backfilled = True  # 未测 → 已测：典型的观测补录
    obs.status = new
    obs.value = body.value
    obs.source = body.source
    session.commit()
    return _out(obs)


@router.get("/by-plot/{plot_id}")
def observations_by_plot(
    plot_id: int, session: Session = Depends(get_session)
) -> list[dict]:
    rows = session.scalars(
        select(TraitObservation)
        .where(TraitObservation.plot_id == plot_id)
        .order_by(TraitObservation.plant_tag, TraitObservation.trait, TraitObservation.id)
    ).all()
    return [_out(o) for o in rows]
