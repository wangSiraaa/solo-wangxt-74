"""人工淘汰/保留决定接口。仅人能改动，自动流程不得触碰。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import DecisionType, Germplasm, SelectionDecision
from ..schemas import DecisionUpsert

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


def _out(d: SelectionDecision) -> dict:
    return {
        "germplasm_code": d.germplasm.code,
        "germplasm_name": d.germplasm.name,
        "decision": d.decision.value,
        "note": d.note,
        "decided_by": d.decided_by,
        "decided_at": d.decided_at.isoformat(),
    }


@router.get("")
def list_decisions(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.scalars(
        select(SelectionDecision).order_by(SelectionDecision.id)
    ).all()
    return [_out(d) for d in rows]


@router.put("/{germplasm_code}")
def upsert_decision(
    germplasm_code: str,
    body: DecisionUpsert,
    session: Session = Depends(get_session),
) -> dict:
    g = session.scalars(
        select(Germplasm).where(Germplasm.code == germplasm_code)
    ).first()
    if g is None:
        raise HTTPException(404, f"材料 {germplasm_code} 不存在")
    row = session.scalars(
        select(SelectionDecision).where(
            SelectionDecision.germplasm_id == g.id
        )
    ).first()
    if row is None:
        row = SelectionDecision(germplasm_id=g.id, decision=body.decision)
        session.add(row)
    row.decision = DecisionType(body.decision)
    row.note = body.note
    row.decided_by = body.decided_by
    row.decided_at = datetime.utcnow()
    session.commit()
    return _out(row)
