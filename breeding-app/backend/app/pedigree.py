"""亲缘图校验与亲本修订。

亲缘图：有向图 亲本 → 后代，禁止环（后代不能成为祖先）。
亲本修订：原交配事件不可变；已确认（CONFIRMED）的修订形成“现行亲本”，
谱系与统计均按现行亲本计算；草案（DRAFT）不影响任何结论。
"""
from __future__ import annotations

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Germplasm,
    MatingEvent,
    MatingType,
    ParentageRevision,
    ParentField,
    Progeny,
    RevisionStatus,
    Trial,
    TrialPlot,
)


class PedigreeError(ValueError):
    """谱系校验失败（应返回 422）。"""


def known_parent_ids(event: MatingEvent) -> list[int]:
    """事件的已知亲本 id（原始记录；未知父本不计入，也绝不虚构）。"""
    ids = [event.female_parent_id]
    if event.male_parent_id is not None and event.male_parent_id not in ids:
        ids.append(event.male_parent_id)
    return ids


def confirmed_revision_map(
    session: Session,
) -> dict[int, dict[ParentField, int | None]]:
    """已确认修订：event_id → {字段: 新亲本 id}，按确认时间先后应用。"""
    revs = session.scalars(
        select(ParentageRevision)
        .where(ParentageRevision.status == RevisionStatus.CONFIRMED)
        .order_by(ParentageRevision.confirmed_at)
    ).all()
    out: dict[int, dict[ParentField, int | None]] = {}
    for rev in revs:
        out.setdefault(rev.mating_event_id, {})[rev.field] = rev.new_parent_id
    return out


def effective_parents(
    session: Session,
    event: MatingEvent,
    rev_map: dict | None = None,
) -> tuple[int | None, int | None]:
    """现行亲本 (母, 父)：原始记录叠加已确认修订。自交事件父本跟随母本。"""
    if rev_map is None:
        rev_map = confirmed_revision_map(session)
    female, male = event.female_parent_id, event.male_parent_id
    overrides = rev_map.get(event.id, {})
    if ParentField.FEMALE in overrides:
        female = overrides[ParentField.FEMALE]
    if ParentField.MALE in overrides:
        male = overrides[ParentField.MALE]
    if event.type == MatingType.SELF:
        male = female
    return female, male


def build_graph(
    session: Session,
    extra_overrides: dict[int, tuple[int | None, int | None]] | None = None,
) -> nx.DiGraph:
    """按现行亲本重建完整亲缘图；extra_overrides 可模拟某事件修订后的亲本。"""
    g = nx.DiGraph()
    g.add_nodes_from(session.scalars(select(Germplasm.id)).all())
    events = {e.id: e for e in session.scalars(select(MatingEvent)).all()}
    rev_map = confirmed_revision_map(session)
    for link in session.scalars(select(Progeny)).all():
        event = events.get(link.mating_event_id)
        if event is None:
            continue
        female, male = effective_parents(session, event, rev_map)
        if extra_overrides and event.id in extra_overrides:
            female, male = extra_overrides[event.id]
        for parent_id in {female, male} - {None}:
            g.add_edge(parent_id, link.germplasm_id, event=event.code)
    return g


def validate_event_parents(
    session: Session,
    mating_type: MatingType,
    female: Germplasm | None,
    male: Germplasm | None,
) -> None:
    """校验亲本组合本身合法（自交/杂交分别建模）。"""
    if female is None:
        raise PedigreeError("母本必须已知并存在于材料库中")
    if mating_type == MatingType.SELF:
        if male is not None and male.id != female.id:
            raise PedigreeError(
                "自交事件的父母本必须相同；不同亲本请使用杂交（CROSS）"
            )
    else:  # CROSS
        if male is not None and male.id == female.id:
            raise PedigreeError(
                "杂交事件的父母本必须不同；同一亲本请使用自交（SELF）"
            )


def assert_can_attach(
    session: Session, event: MatingEvent, child: Germplasm
) -> None:
    """校验可以把 child 登记为 event 的后代（环检测）。"""
    existing = session.scalars(
        select(Progeny).where(Progeny.germplasm_id == child.id)
    ).first()
    if existing is not None:
        raise PedigreeError(
            f"材料 {child.code} 已有来源交配事件，不能重复登记亲本"
        )

    graph = build_graph(session)
    for parent_id in known_parent_ids(event):
        if parent_id == child.id:
            raise PedigreeError(f"材料 {child.code} 不能作为自己的亲本")
        if graph.has_node(child.id) and nx.has_path(graph, child.id, parent_id):
            raise PedigreeError(
                f"禁止登记：{child.code} 是该亲本的后代，后代不能成为祖先"
            )


def validate_revision(
    session: Session,
    event: MatingEvent,
    field: ParentField,
    new_parent_id: int | None,
) -> None:
    """校验修订若生效是否合法：世代循环（指出路径）或未知来源均阻止。"""
    cur_female, cur_male = effective_parents(session, event)
    new_female, new_male = cur_female, cur_male
    if event.type == MatingType.SELF and field == ParentField.MALE:
        raise PedigreeError("自交事件请修订母本字段，父本自动跟随母本")
    if field == ParentField.FEMALE:
        new_female = new_parent_id
    else:
        new_male = new_parent_id
    if event.type == MatingType.SELF:
        new_male = new_female

    # 未知来源：修订后后代没有任何已知亲本
    if new_female is None and new_male is None:
        raise PedigreeError(
            "修订将导致后代没有任何已知亲本（来源未知），阻止生效"
        )
    # 杂交父母本不得相同（同一亲本应建模为自交）
    if (
        event.type == MatingType.CROSS
        and new_female is not None
        and new_female == new_male
    ):
        raise PedigreeError("修订后父母本相同；同一亲本应建模为自交（SELF）")

    # 世代循环：新亲本是该事件某后代的后代 ⇒ 指出路径
    graph = build_graph(session)
    offspring_ids = [l.germplasm_id for l in event.progeny_links]
    for parent_id in {new_female, new_male} - {None}:
        for child_id in offspring_ids:
            if parent_id == child_id:
                code = session.get(Germplasm, child_id).code
                raise PedigreeError(
                    f"修订将造成世代循环：{code} 不能作为自己的亲本"
                )
            if graph.has_node(child_id) and nx.has_path(
                graph, child_id, parent_id
            ):
                path = nx.shortest_path(graph, child_id, parent_id)
                codes = [session.get(Germplasm, i).code for i in path]
                raise PedigreeError(
                    "修订将造成世代循环，路径：" + " → ".join(codes)
                )


def revision_impact(session: Session, event: MatingEvent) -> dict:
    """修订影响分析：分别列出谱系受影响与家系统计受影响的后代。

    - 谱系受影响：事件的全部后代及其所有下游后裔（祖先集合改变）；
    - 统计受影响：仅事件的直接后代（其家系=亲本组合改变，观测随小区重分组）。
    """
    graph = build_graph(session)
    offspring = [l.germplasm for l in event.progeny_links]
    affected_ids = {o.id for o in offspring}
    for o in offspring:
        if graph.has_node(o.id):
            affected_ids |= nx.descendants(graph, o.id)

    def brief(gid: int) -> dict:
        g = session.get(Germplasm, gid)
        return {"code": g.code, "name": g.name, "generation": g.generation}

    plots = session.scalars(
        select(TrialPlot).where(TrialPlot.family_id == event.id)
    ).all()
    trial_ids = sorted({p.trial_id for p in plots})
    return {
        "pedigree_affected": [brief(i) for i in sorted(affected_ids)],
        "stats_affected": [brief(o.id) for o in offspring],
        "affected_trials": [
            {"id": t, "name": session.get(Trial, t).name} for t in trial_ids
        ],
    }


def ancestors(session: Session, germplasm_id: int) -> list[int]:
    graph = build_graph(session)
    if not graph.has_node(germplasm_id):
        return []
    return sorted(nx.ancestors(graph, germplasm_id))


def descendants(session: Session, germplasm_id: int) -> list[int]:
    graph = build_graph(session)
    if not graph.has_node(germplasm_id):
        return []
    return sorted(nx.descendants(graph, germplasm_id))
