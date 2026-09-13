"""发布结果版本与待确认重算接口。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import (
    PublishedResult,
    RecalcProposal,
    RecalcStatus,
    Trial,
)
from ..schemas import PublishCreate, RecalcResolve
from ..stats import family_stats

router = APIRouter(prefix="/api", tags=["results"])


def _pub_out(p: PublishedResult) -> dict:
    return {
        "id": p.id,
        "trial_id": p.trial_id,
        "trait": p.trait,
        "version": p.version,
        "published_by": p.published_by,
        "published_at": p.published_at.isoformat(),
    }


def _recalc_out(session: Session, r: RecalcProposal) -> dict:
    trial = session.get(Trial, r.trial_id)
    return {
        "code": r.code,
        "trial_id": r.trial_id,
        "trial_name": trial.name if trial else "",
        "trait": r.trait,
        "based_version": r.based_version,
        "revision_code": r.revision.code,
        "status": r.status.value,
        "resolver": r.resolver,
        "created_at": r.created_at.isoformat(),
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
    }


@router.post("/trials/{trial_id}/publish", status_code=201)
def publish_result(
    trial_id: int, body: PublishCreate, session: Session = Depends(get_session)
) -> dict:
    """把当前（现行亲本下的）家系统计发布为新的不可变版本。"""
    if session.get(Trial, trial_id) is None:
        raise HTTPException(404, f"试验 {trial_id} 不存在")
    payload = family_stats(session, trial_id, body.trait)
    latest = session.scalars(
        select(PublishedResult)
        .where(
            PublishedResult.trial_id == trial_id,
            PublishedResult.trait == body.trait,
        )
        .order_by(PublishedResult.version.desc())
    ).first()
    pub = PublishedResult(
        trial_id=trial_id,
        trait=body.trait,
        version=(latest.version + 1) if latest else 1,
        payload=payload,
        published_by=body.published_by,
    )
    session.add(pub)
    session.commit()
    return _pub_out(pub)


@router.get("/trials/{trial_id}/publications")
def list_publications(
    trial_id: int, trait: str = "", session: Session = Depends(get_session)
) -> list[dict]:
    stmt = select(PublishedResult).where(PublishedResult.trial_id == trial_id)
    if trait:
        stmt = stmt.where(PublishedResult.trait == trait)
    pubs = session.scalars(
        stmt.order_by(PublishedResult.trait, PublishedResult.version)
    ).all()
    return [_pub_out(p) for p in pubs]


@router.get("/publications/{pub_id}")
def publication_detail(pub_id: int, session: Session = Depends(get_session)) -> dict:
    pub = session.get(PublishedResult, pub_id)
    if pub is None:
        raise HTTPException(404, f"发布版本 {pub_id} 不存在")
    out = _pub_out(pub)
    out["payload"] = pub.payload
    return out


@router.get("/recalc")
def list_recalc(
    status: str = "", session: Session = Depends(get_session)
) -> list[dict]:
    stmt = select(RecalcProposal).order_by(RecalcProposal.code)
    if status:
        stmt = stmt.where(RecalcProposal.status == RecalcStatus(status))
    return [_recalc_out(session, r) for r in session.scalars(stmt).all()]


@router.get("/recalc/{code}")
def recalc_detail(code: str, session: Session = Depends(get_session)) -> dict:
    prop = session.scalars(
        select(RecalcProposal).where(RecalcProposal.code == code)
    ).first()
    if prop is None:
        raise HTTPException(404, f"重算提案 {code} 不存在")
    out = _recalc_out(session, prop)
    out["payload"] = prop.payload
    return out


@router.post("/recalc/{code}/approve")
def approve_recalc(
    code: str, body: RecalcResolve, session: Session = Depends(get_session)
) -> dict:
    """批准重算：形成新的发布版本。不触碰任何人工淘汰/保留决定。"""
    prop = session.scalars(
        select(RecalcProposal).where(RecalcProposal.code == code)
    ).first()
    if prop is None:
        raise HTTPException(404, f"重算提案 {code} 不存在")
    if prop.status != RecalcStatus.PENDING:
        raise HTTPException(422, f"重算提案 {code} 已处理（{prop.status.value}）")

    latest = session.scalars(
        select(PublishedResult)
        .where(
            PublishedResult.trial_id == prop.trial_id,
            PublishedResult.trait == prop.trait,
        )
        .order_by(PublishedResult.version.desc())
    ).first()
    pub = PublishedResult(
        trial_id=prop.trial_id,
        trait=prop.trait,
        version=(latest.version + 1) if latest else 1,
        payload=prop.payload,
        published_by=body.resolver,
    )
    session.add(pub)
    prop.status = RecalcStatus.APPROVED
    prop.resolver = body.resolver
    prop.resolved_at = datetime.utcnow()
    session.commit()
    return {"recalc": _recalc_out(session, prop), "publication": _pub_out(pub)}


@router.post("/recalc/{code}/reject")
def reject_recalc(
    code: str, body: RecalcResolve, session: Session = Depends(get_session)
) -> dict:
    """驳回重算：旧发布版本继续有效。"""
    prop = session.scalars(
        select(RecalcProposal).where(RecalcProposal.code == code)
    ).first()
    if prop is None:
        raise HTTPException(404, f"重算提案 {code} 不存在")
    if prop.status != RecalcStatus.PENDING:
        raise HTTPException(422, f"重算提案 {code} 已处理（{prop.status.value}）")
    prop.status = RecalcStatus.REJECTED
    prop.resolver = body.resolver
    prop.resolved_at = datetime.utcnow()
    session.commit()
    return _recalc_out(session, prop)
