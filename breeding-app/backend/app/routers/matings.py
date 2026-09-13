"""交配事件接口：登记杂交/自交与后代，NetworkX 校验无环。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..codes import next_code
from ..database import get_session
from ..models import Germplasm, MatingEvent, MatingType, Progeny
from ..pedigree import (
    PedigreeError,
    assert_can_attach,
    effective_parents,
    known_parent_ids,
    validate_event_parents,
)
from ..schemas import MatingCreate

router = APIRouter(prefix="/api/matings", tags=["matings"])


def _brief(g: Germplasm | None) -> dict | None:
    return {"code": g.code, "name": g.name} if g is not None else None


def _event_out(e: MatingEvent, session: Session) -> dict:
    eff_female_id, eff_male_id = effective_parents(session, e)
    eff_female = session.get(Germplasm, eff_female_id) if eff_female_id else None
    eff_male = session.get(Germplasm, eff_male_id) if eff_male_id else None
    return {
        "code": e.code,
        "type": e.type.value,
        "season": e.season,
        "notes": e.notes,
        # 原始记录（永不被覆盖）
        "female": _brief(e.female_parent),
        "male": _brief(e.male_parent),
        # 现行亲本（原始记录 + 已确认修订）
        "female_effective": _brief(eff_female),
        "male_effective": _brief(eff_male),
        "offspring": [
            {"code": l.germplasm.code, "name": l.germplasm.name,
             "generation": l.germplasm.generation}
            for l in e.progeny_links
        ],
    }


@router.get("")
def list_matings(session: Session = Depends(get_session)) -> list[dict]:
    events = session.scalars(select(MatingEvent).order_by(MatingEvent.code)).all()
    return [_event_out(e, session) for e in events]


@router.post("", status_code=201)
def create_mating(
    body: MatingCreate, session: Session = Depends(get_session)
) -> dict:
    female = session.scalars(
        select(Germplasm).where(Germplasm.code == body.female_code)
    ).first()
    male = None
    if body.male_code:
        male = session.scalars(
            select(Germplasm).where(Germplasm.code == body.male_code)
        ).first()
        if male is None:
            raise HTTPException(404, f"父本 {body.male_code} 不存在；未知父本请留空，不要编造编号")

    try:
        validate_event_parents(session, body.type, female, male)
    except PedigreeError as exc:
        raise HTTPException(422, str(exc))

    # 自交：父本=母本（显式存储，与杂交区分建模）
    male_id = None
    if body.type == MatingType.SELF:
        male_id = female.id
    elif male is not None:
        male_id = male.id

    event = MatingEvent(
        code=next_code(session, MatingEvent, "ME"),
        type=body.type,
        female_parent_id=female.id,
        male_parent_id=male_id,
        season=body.season,
        notes=body.notes,
    )
    session.add(event)
    session.flush()

    parent_gen = max(
        session.get(Germplasm, pid).generation for pid in known_parent_ids(event)
    )
    child_gen = parent_gen + 1  # 混合世代：取已知亲本最高世代 + 1

    # 新后代：按名称登记（允许与已有材料重名，编号区分）
    for name in body.offspring_names:
        child = Germplasm(
            code=next_code(session, Germplasm, "GM"),
            name=name,
            generation=child_gen,
        )
        session.add(child)
        session.flush()
        session.add(Progeny(mating_event_id=event.id, germplasm_id=child.id))
        session.flush()

    # 挂接已有材料：补录历史谱系，必须过环校验
    for code in body.offspring_codes:
        child = session.scalars(
            select(Germplasm).where(Germplasm.code == code)
        ).first()
        if child is None:
            raise HTTPException(404, f"后代材料 {code} 不存在")
        try:
            assert_can_attach(session, event, child)
        except PedigreeError as exc:
            raise HTTPException(422, str(exc))
        child.generation = child_gen
        session.add(Progeny(mating_event_id=event.id, germplasm_id=child.id))
        session.flush()

    session.commit()
    session.refresh(event)
    return _event_out(event, session)


@router.get("/{code}")
def mating_detail(code: str, session: Session = Depends(get_session)) -> dict:
    event = session.scalars(
        select(MatingEvent).where(MatingEvent.code == code)
    ).first()
    if event is None:
        raise HTTPException(404, f"交配事件 {code} 不存在")
    return _event_out(event, session)
