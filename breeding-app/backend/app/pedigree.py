"""亲缘图校验：用 NetworkX 有向图（亲本 → 后代）保证谱系无环。

核心规则：禁止后代成为祖先——新增 亲本→后代 边之前，
若图中已存在 后代→…→亲本 的路径，则拒绝。
"""
from __future__ import annotations

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Germplasm, MatingEvent, MatingType, Progeny


class PedigreeError(ValueError):
    """谱系校验失败（应返回 422）。"""


def known_parent_ids(event: MatingEvent) -> list[int]:
    """事件的已知亲本 id（未知父本不计入，也绝不虚构）。"""
    ids = [event.female_parent_id]
    if event.male_parent_id is not None and event.male_parent_id not in ids:
        ids.append(event.male_parent_id)
    return ids


def build_graph(session: Session) -> nx.DiGraph:
    """从当前会话（含未提交但已 flush 的数据）重建完整亲缘图。"""
    g = nx.DiGraph()
    g.add_nodes_from(session.scalars(select(Germplasm.id)).all())
    links = session.scalars(select(Progeny)).all()
    events = {
        e.id: e for e in session.scalars(select(MatingEvent)).all()
    }
    for link in links:
        event = events.get(link.mating_event_id)
        if event is None:
            continue
        for parent_id in known_parent_ids(event):
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
    """校验可以把 child 登记为 event 的后代。

    - 每个材料至多一个来源交配事件；
    - 禁止后代成为祖先（环检测）。
    """
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
            raise PedigreeError(
                f"材料 {child.code} 不能作为自己的亲本"
            )
        # child 已是 parent 的祖先 ⇒ 新增 parent→child 会成环
        if graph.has_node(child.id) and nx.has_path(graph, child.id, parent_id):
            raise PedigreeError(
                f"禁止登记：{child.code} 是该亲本的后代，后代不能成为祖先"
            )


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
