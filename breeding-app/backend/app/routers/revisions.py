"""亲本修订接口：草案 → (证据+确认人) 确认生效 / 驳回。

原交配事件永不被覆盖；确认时校验：
- 证据非空、确认人非空且 ≠ 提出人（证据不足不得作为确定结论）；
- 不得与同事件同字段的其他矛盾草案并存；
- 不得造成世代循环（指出路径）或未知来源。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..codes import next_code
from ..database import get_session
from ..models import (
    Germplasm,
    MatingEvent,
    ParentageRevision,
    ParentField,
    RevisionStatus,
)
from ..pedigree import (
    PedigreeError,
    effective_parents,
    revision_impact,
    validate_revision,
)
from ..schemas import RevisionConfirm, RevisionCreate, RevisionReject
from ..stats import create_recalc_proposals

router = APIRouter(prefix="/api/revisions", tags=["revisions"])


def _parent_brief(session: Session, pid: int | None) -> dict | None:
    if pid is None:
        return None
    g = session.get(Germplasm, pid)
    return {"code": g.code, "name": g.name} if g else None


def _conflicts(session: Session, rev: ParentageRevision) -> list[str]:
    """同事件同字段、目标不同的其他草案（相互矛盾）。"""
    others = session.scalars(
        select(ParentageRevision).where(
            ParentageRevision.mating_event_id == rev.mating_event_id,
            ParentageRevision.field == rev.field,
            ParentageRevision.status == RevisionStatus.DRAFT,
            ParentageRevision.id != rev.id,
        )
    ).all()
    return [o.code for o in others if o.new_parent_id != rev.new_parent_id]


def _out(session: Session, rev: ParentageRevision) -> dict:
    return {
        "code": rev.code,
        "event_code": rev.mating_event.code,
        "field": rev.field.value,
        "old_parent": _parent_brief(session, rev.old_parent_id),
        "new_parent": _parent_brief(session, rev.new_parent_id),
        "evidence": rev.evidence,
        "proposer": rev.proposer,
        "confirmer": rev.confirmer,
        "status": rev.status.value,
        "created_at": rev.created_at.isoformat(),
        "confirmed_at": rev.confirmed_at.isoformat() if rev.confirmed_at else None,
        "conflicts_with": (
            _conflicts(session, rev) if rev.status == RevisionStatus.DRAFT else []
        ),
    }


def _blocking_issue(session: Session, rev: ParentageRevision) -> str | None:
    try:
        validate_revision(session, rev.mating_event, rev.field, rev.new_parent_id)
        return None
    except PedigreeError as exc:
        return str(exc)


@router.get("")
def list_revisions(session: Session = Depends(get_session)) -> list[dict]:
    revs = session.scalars(
        select(ParentageRevision).order_by(ParentageRevision.code)
    ).all()
    return [_out(session, r) for r in revs]


@router.post("", status_code=201)
def create_revision(
    body: RevisionCreate, session: Session = Depends(get_session)
) -> dict:
    event = session.scalars(
        select(MatingEvent).where(MatingEvent.code == body.event_code)
    ).first()
    if event is None:
        raise HTTPException(404, f"交配事件 {body.event_code} 不存在")

    new_parent = None
    if body.new_parent_code:
        new_parent = session.scalars(
            select(Germplasm).where(Germplasm.code == body.new_parent_code)
        ).first()
        if new_parent is None:
            raise HTTPException(
                404,
                f"材料 {body.new_parent_code} 不存在；"
                "若亲本未知请将新亲本留空，不要编造编号",
            )

    # 旧值取“现行亲本”快照（原始记录 + 已确认修订）
    cur_female, cur_male = effective_parents(session, event)
    old_parent_id = cur_female if body.field == ParentField.FEMALE else cur_male

    rev = ParentageRevision(
        code=next_code(session, ParentageRevision, "RV"),
        mating_event_id=event.id,
        field=body.field,
        old_parent_id=old_parent_id,
        new_parent_id=new_parent.id if new_parent else None,
        evidence=body.evidence,
        proposer=body.proposer,
    )
    session.add(rev)
    session.flush()
    session.commit()
    out = _out(session, rev)
    out["impact"] = revision_impact(session, event)
    out["blocking_issue"] = _blocking_issue(session, rev)
    return out


@router.get("/{code}")
def revision_detail(code: str, session: Session = Depends(get_session)) -> dict:
    rev = session.scalars(
        select(ParentageRevision).where(ParentageRevision.code == code)
    ).first()
    if rev is None:
        raise HTTPException(404, f"修订 {code} 不存在")
    out = _out(session, rev)
    out["impact"] = revision_impact(session, rev.mating_event)
    out["blocking_issue"] = _blocking_issue(session, rev)
    return out


@router.post("/{code}/confirm")
def confirm_revision(
    code: str, body: RevisionConfirm, session: Session = Depends(get_session)
) -> dict:
    rev = session.scalars(
        select(ParentageRevision).where(ParentageRevision.code == code)
    ).first()
    if rev is None:
        raise HTTPException(404, f"修订 {code} 不存在")
    if rev.status != RevisionStatus.DRAFT:
        raise HTTPException(422, f"修订 {code} 当前状态为 {rev.status.value}，不能确认")

    # 证据与确认人：证据不足的亲本不得当成确定结论
    if not rev.evidence.strip():
        raise HTTPException(422, "证据不足：请先在草案中补充证据，不能作为确定结论")
    if body.confirmer.strip() == rev.proposer.strip():
        raise HTTPException(422, "确认人不能与提出人相同（需第二人核对）")

    # 相互矛盾的草案：须先驳回或撤回
    conflicts = _conflicts(session, rev)
    if conflicts:
        raise HTTPException(
            409,
            "存在相互矛盾的修订草案：" + "、".join(conflicts) + "，请先驳回或撤回",
        )

    # 世代循环 / 未知来源：阻止生效并指出路径
    try:
        validate_revision(session, rev.mating_event, rev.field, rev.new_parent_id)
    except PedigreeError as exc:
        raise HTTPException(422, str(exc))

    # 同字段旧的已确认修订转为 SUPERSEDED（保留历史，不删除）
    for old in session.scalars(
        select(ParentageRevision).where(
            ParentageRevision.mating_event_id == rev.mating_event_id,
            ParentageRevision.field == rev.field,
            ParentageRevision.status == RevisionStatus.CONFIRMED,
        )
    ).all():
        old.status = RevisionStatus.SUPERSEDED

    rev.status = RevisionStatus.CONFIRMED
    rev.confirmer = body.confirmer.strip()
    rev.confirmed_at = datetime.utcnow()
    session.flush()

    # 新分组形成“待确认的重算”（不自动改动已发布版本与人工决定）
    proposals = create_recalc_proposals(session, rev)
    session.commit()
    return {
        "revision": _out(session, rev),
        "recalc_proposals": [p.code for p in proposals],
    }


@router.post("/{code}/reject")
def reject_revision(
    code: str, body: RevisionReject, session: Session = Depends(get_session)
) -> dict:
    rev = session.scalars(
        select(ParentageRevision).where(ParentageRevision.code == code)
    ).first()
    if rev is None:
        raise HTTPException(404, f"修订 {code} 不存在")
    if rev.status != RevisionStatus.DRAFT:
        raise HTTPException(422, f"修订 {code} 当前状态为 {rev.status.value}，不能驳回")
    rev.status = RevisionStatus.REJECTED
    session.commit()
    return _out(session, rev)
