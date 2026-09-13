"""材料（germplasm）接口：登记、查询、谱系、来源回溯。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..codes import next_code
from ..database import get_session
from ..models import (
    Germplasm,
    MatingEvent,
    ParentageRevision,
    Progeny,
    TraitObservation,
    TrialPlot,
    Trial,
)
from ..pedigree import ancestors, build_graph, descendants, effective_parents
from ..schemas import GermplasmCreate, GermplasmRename

router = APIRouter(prefix="/api/germplasm", tags=["germplasm"])


def _out(g: Germplasm) -> dict:
    return {
        "id": g.id,
        "code": g.code,
        "name": g.name,
        "generation": g.generation,
        "notes": g.notes,
    }


def _get_by_code(session: Session, code: str) -> Germplasm:
    g = session.scalars(select(Germplasm).where(Germplasm.code == code)).first()
    if g is None:
        raise HTTPException(404, f"材料 {code} 不存在")
    return g


def _parent_ref(session: Session, pid: int | None) -> dict | None:
    if pid is None:
        return None
    g = session.get(Germplasm, pid)
    return {"code": g.code, "name": g.name} if g else None


@router.get("")
def list_germplasm(
    search: str = "", session: Session = Depends(get_session)
) -> list[dict]:
    stmt = select(Germplasm).order_by(Germplasm.code)
    if search:
        stmt = stmt.where(
            Germplasm.name.contains(search) | Germplasm.code.contains(search)
        )
    return [_out(g) for g in session.scalars(stmt).all()]


@router.post("", status_code=201)
def create_germplasm(
    body: GermplasmCreate, session: Session = Depends(get_session)
) -> dict:
    """登记基础材料（无来源交配事件）。同名允许，靠稳定编号区分。"""
    g = Germplasm(
        code=next_code(session, Germplasm, "GM"),
        name=body.name,
        generation=body.generation,
        notes=body.notes,
    )
    session.add(g)
    session.commit()
    return _out(g)


@router.get("/{code}")
def germplasm_detail(code: str, session: Session = Depends(get_session)) -> dict:
    g = _get_by_code(session, code)
    out = _out(g)
    link = session.scalars(
        select(Progeny).where(Progeny.germplasm_id == g.id)
    ).first()
    out["origin_event"] = link.mating_event.code if link else None
    return out


@router.patch("/{code}")
def rename_germplasm(
    code: str, body: GermplasmRename, session: Session = Depends(get_session)
) -> dict:
    """改名：名称可变，稳定编号与谱系身份不变。"""
    g = _get_by_code(session, code)
    g.name = body.name
    session.commit()
    return _out(g)


@router.get("/{code}/pedigree")
def pedigree(code: str, session: Session = Depends(get_session)) -> dict:
    """祖先/后代视图。未知父本在图中不存在节点，前端显示“未知”，不补全。"""
    g = _get_by_code(session, code)
    graph = build_graph(session)
    anc_ids = ancestors(session, g.id)
    desc_ids = descendants(session, g.id)

    nodes = {
        x.id: x
        for x in session.scalars(
            select(Germplasm).where(Germplasm.id.in_([g.id, *anc_ids, *desc_ids]))
        ).all()
    }
    # 相关边（含交配事件号，便于回溯）
    events = {e.id: e for e in session.scalars(select(MatingEvent)).all()}
    edges = []
    for link in session.scalars(select(Progeny)).all():
        event = events[link.mating_event_id]
        parents = [event.female_parent_id]
        if event.male_parent_id is not None and event.male_parent_id != event.female_parent_id:
            parents.append(event.male_parent_id)
        for pid in parents:
            if pid in nodes and link.germplasm_id in nodes:
                edges.append(
                    {
                        "parent": nodes[pid].code,
                        "child": nodes[link.germplasm_id].code,
                        "event": event.code,
                        "type": event.type.value,
                    }
                )
    return {
        "focus": _out(g),
        "ancestors": [_out(nodes[i]) for i in anc_ids],
        "descendants": [_out(nodes[i]) for i in desc_ids],
        "edges": edges,
    }


@router.get("/{code}/trace")
def trace(code: str, session: Session = Depends(get_session)) -> dict:
    """来源回溯：该材料的交配来源 + 全部观测记录（含补录与来源）。"""
    g = _get_by_code(session, code)

    origin = None
    link = session.scalars(
        select(Progeny).where(Progeny.germplasm_id == g.id)
    ).first()
    if link is not None:
        event = link.mating_event
        siblings = [
            l.germplasm.code
            for l in event.progeny_links
            if l.germplasm_id != g.id
        ]
        # 现行亲本（原始记录 + 已确认修订）；原始记录一并返回，不被覆盖
        eff_female_id, eff_male_id = effective_parents(session, event)
        revisions = session.scalars(
            select(ParentageRevision)
            .where(ParentageRevision.mating_event_id == event.id)
            .order_by(ParentageRevision.code)
        ).all()
        origin = {
            "event_code": event.code,
            "type": event.type.value,
            "season": event.season,
            "female": _parent_ref(session, eff_female_id),
            "male": _parent_ref(session, eff_male_id),
            "female_original": {
                "code": event.female_parent.code,
                "name": event.female_parent.name,
            },
            "male_original": (
                {"code": event.male_parent.code, "name": event.male_parent.name}
                if event.male_parent is not None
                else None  # 未知父本：如实返回空，不伪造
            ),
            "revisions": [
                {
                    "code": r.code,
                    "field": r.field.value,
                    "old_parent": _parent_ref(session, r.old_parent_id),
                    "new_parent": _parent_ref(session, r.new_parent_id),
                    "status": r.status.value,
                    "evidence": r.evidence,
                    "proposer": r.proposer,
                    "confirmer": r.confirmer,
                }
                for r in revisions
            ],
            "siblings": siblings,
        }

    obs_rows = session.scalars(
        select(TraitObservation)
        .where(TraitObservation.germplasm_id == g.id)
        .order_by(TraitObservation.observed_on)
    ).all()
    observations = []
    for o in obs_rows:
        plot = o.plot
        trial = session.get(Trial, plot.trial_id)
        observations.append(
            {
                "id": o.id,
                "trial": trial.name if trial else "",
                "plot_label": plot.label,
                "replicate": plot.replicate,
                "plant_tag": o.plant_tag,
                "trait": o.trait,
                "status": o.status.value,
                "value": o.value,
                "observed_on": o.observed_on.isoformat(),
                "source": o.source,
                "backfilled": o.backfilled,
                "created_at": o.created_at.isoformat(),
                "updated_at": o.updated_at.isoformat(),
            }
        )
    return {"germplasm": _out(g), "origin": origin, "observations": observations}
