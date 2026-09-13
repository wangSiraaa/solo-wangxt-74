"""虚构演示数据：虚构作物“蓝穗谷”，全部材料、数值均为虚构。

覆盖场景：同名材料、自交与杂交、未知父本、混合世代、
真实零值 / 未测 / 死亡、同株多次测定、标签丢失、观测补录。
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .codes import next_code
from .models import (
    DecisionType,
    Germplasm,
    MatingEvent,
    MatingType,
    ObsStatus,
    ParentageRevision,
    ParentField,
    Progeny,
    PublishedResult,
    SelectionDecision,
    TraitObservation,
    Trial,
    TrialPlot,
)


def _g(session: Session, name: str, generation: int, notes: str = "") -> Germplasm:
    g = Germplasm(
        code=next_code(session, Germplasm, "GM"),
        name=name,
        generation=generation,
        notes=notes,
    )
    session.add(g)
    session.flush()
    return g


def _event(
    session: Session,
    mtype: MatingType,
    female: Germplasm,
    male: Germplasm | None,
    season: str,
    offspring: list[str],
) -> MatingEvent:
    e = MatingEvent(
        code=next_code(session, MatingEvent, "ME"),
        type=mtype,
        female_parent_id=female.id,
        male_parent_id=male.id if male else (female.id if mtype == MatingType.SELF else None),
        season=season,
    )
    session.add(e)
    session.flush()
    gen = max(p.generation for p in {female, male} if p) + 1
    for name in offspring:
        child = _g(session, name, gen)
        session.add(Progeny(mating_event_id=e.id, germplasm_id=child.id))
        session.flush()
    return e


def seed_if_empty(session: Session) -> bool:
    if session.scalars(select(Germplasm.id).limit(1)).first() is not None:
        return False

    # ---- 基础材料（含同名：两个“矮秆优系”只能靠编号区分）----
    a1 = _g(session, "高穗优系", 0)
    a2 = _g(session, "早熟优系", 0)
    a3 = _g(session, "矮秆优系", 0, "同名材料之一（北圃选留）")
    a4 = _g(session, "抗病优系", 0)
    a5 = _g(session, "矮秆优系", 0, "同名材料之二（南圃选留）")

    # ---- 交配事件 ----
    e1 = _event(session, MatingType.CROSS, a1, a2, "2024-春", ["蓝穗F1-甲", "蓝穗F1-乙"])
    f1a = session.scalars(select(Germplasm).where(Germplasm.name == "蓝穗F1-甲")).one()
    f1b = session.scalars(select(Germplasm).where(Germplasm.name == "蓝穗F1-乙")).one()

    e2 = _event(session, MatingType.SELF, f1a, None, "2024-秋", ["蓝穗F2-1", "蓝穗F2-2"])
    f2_1 = session.scalars(select(Germplasm).where(Germplasm.name == "蓝穗F2-1")).one()

    # 混合世代：F2 × 基础材料（0 代）
    e3 = _event(session, MatingType.CROSS, f2_1, a4, "2025-春", ["蓝穗BC1-1", "蓝穗BC1-2"])
    # 未知父本（标签丢失的混合花粉）：male=None，绝不伪造
    e4 = _event(session, MatingType.CROSS, f1b, None, "2025-春", ["蓝穗半同胞-1"])
    e5 = _event(session, MatingType.SELF, a5, None, "2025-春", ["矮秆S1-1"])

    # ---- 试验与小区（2 重复）----
    trial = Trial(name="2026春 蓝穗谷产量鉴定圃", season="2026-春")
    session.add(trial)
    session.flush()
    fam_events = [e1, e2, e3, e4, e5]
    plots: list[TrialPlot] = []
    for rep in (1, 2):
        for i, ev in enumerate(fam_events, start=1):
            p = TrialPlot(
                trial_id=trial.id,
                label=f"R{rep}-{i:02d}",
                replicate=rep,
                family_id=ev.id,
            )
            session.add(p)
            plots.append(p)
    session.flush()

    # ---- 观测：株高cm、单穗粒重g ----
    def obs(plot, tag, trait, status, value=None, germ=None, src="田间记载-李", backfilled=False):
        o = TraitObservation(
            plot_id=plot.id,
            plant_tag=tag,
            germplasm_id=germ.id if germ else None,
            trait=trait,
            status=status,
            value=value,
            observed_on=date(2026, 6, 20),
            source=src,
            backfilled=backfilled,
        )
        session.add(o)
        return o

    M, X, D = ObsStatus.MEASURED, ObsStatus.MISSING, ObsStatus.DEAD
    p1, p2 = plots[0], plots[5]  # e1 家系的两个重复小区
    # 同株两次测定（株内平均，不算独立重复）
    obs(p1, "P01", "株高cm", M, 98.0, germ=f1a)
    obs(p1, "P01", "株高cm", M, 102.0, germ=f1a, src="复核-王")
    obs(p1, "P02", "株高cm", M, 110.0, germ=f1b)
    obs(p1, "P03", "株高cm", M, 0.0, germ=f1a, src="田间记载-李")  # 真实零值（倒伏贴地）
    obs(p1, "P04", "株高cm", X)                                   # 未测
    obs(p1, "P05", "株高cm", D)                                   # 死亡
    obs(p1, "P06", "株高cm", M, 95.0, germ=None)                  # 标签丢失
    obs(p2, "P01", "株高cm", M, 105.0, germ=f1a)
    obs(p2, "P02", "株高cm", M, 100.0, germ=f1b)
    obs(p2, "P03", "株高cm", X)

    # 其余小区给家系均值提供数据
    import itertools, random

    rng = random.Random(42)
    for plot in plots:
        if plot in (p1, p2):
            continue
        for j in range(1, 6):
            v = round(rng.uniform(85.0, 120.0), 1)
            obs(plot, f"P{j:02d}", "株高cm", M, v)
        obs(plot, "P06", "株高cm", X)

    # 一条补录示例：先未测，后补录为已测
    late = obs(p2, "P03", "单穗粒重g", X)
    session.flush()
    late.status = M
    late.value = 3.2
    late.source = "考种补录-赵"
    late.backfilled = True

    # ---- 已发布结果（旧家系口径，保留版本）----
    from .stats import family_stats

    session.add(
        PublishedResult(
            trial_id=trial.id,
            trait="株高cm",
            version=1,
            payload=family_stats(session, trial.id, "株高cm"),
            published_by="王老师",
        )
    )

    # ---- 人工淘汰/保留决定（自动流程不得改动）----
    bc1_1 = session.scalars(
        select(Germplasm).where(Germplasm.name == "蓝穗BC1-1")
    ).one()
    session.add(
        SelectionDecision(
            germplasm_id=f2_1.id, decision=DecisionType.KEPT,
            decided_by="李老师", note="株型紧凑，留种",
        )
    )
    session.add(
        SelectionDecision(
            germplasm_id=bc1_1.id, decision=DecisionType.CULLED,
            decided_by="李老师", note="感病重，淘汰",
        )
    )

    # ---- 一个待处理的亲本修订草案（父本记录存疑）----
    session.add(
        ParentageRevision(
            code=next_code(session, ParentageRevision, "RV"),
            mating_event_id=e1.id,
            field=ParentField.MALE,
            old_parent_id=a2.id,
            new_parent_id=a4.id,
            evidence="授粉标签照片#2024-117：父本疑似抗病优系，非早熟优系",
            proposer="李",
        )
    )

    session.commit()
    return True
