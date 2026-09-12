"""编号工具：稳定编号 GM-0001 / ME-0001，全局唯一、不重用在先编号。"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session


def next_code(session: Session, model, prefix: str) -> str:
    codes = session.scalars(select(model.code)).all()
    top = 0
    for code in codes:
        m = re.fullmatch(rf"{prefix}-(\d+)", code or "")
        if m:
            top = max(top, int(m.group(1)))
    return f"{prefix}-{top + 1:04d}"
