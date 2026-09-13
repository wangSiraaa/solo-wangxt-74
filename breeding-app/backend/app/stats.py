"""家系统计：按“小区 × 重复”口径聚合。

口径约定（与育种田间试验一致）：
1. 株为最小观测单位：同株多次测定先在株内平均，不作为独立重复；
2. 小区均值为该小区内全部“已测株”的株均值之平均；
3. 家系均值为各小区均值之平均（小区是试验单位，不按株数加权）；
4. 未测（MISSING）与死亡（DEAD）不进入均值，只分别计数；
   真实零值（MEASURED 且 value=0.0）正常进入均值并单独计数；
5. 株状态判定：任一观测为 DEAD ⇒ 死亡；否则任一 MEASURED ⇒ 已测；
   否则为未测。

家系分组：按交配事件的“现行亲本组合”（原始记录叠加已确认修订）。
亲本修订生效后，对应小区的观测随之重分组——只移动、不复制，
总样本量不变。
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from .codes import next_code
from .models import (
    Germplasm,
    MatingEvent,
    ObsStatus,
    PublishedResult,
    RecalcProposal,
    TraitObservation,
    Trial,
    TrialPlot,
)
from .pedigree import confirmed_revision_map, effective_parents


def _plant_outcome(obs_list: list[TraitObservation]) -> tuple[str, float | None]:
    """归并同株多条观测 → (状态, 株均值)。"""
    statuses = {o.status for o in obs_list}
    if ObsStatus.DEAD in statuses:
        return "dead", None
    measured = [o.value for o in obs_list if o.status == ObsStatus.MEASURED]
    if measured:
        return "measured", mean(measured)
    return "missing", None


def family_stats(session: Session, trial_id: int, trait: str) -> dict:
    trial = session.get(Trial, trial_id)
    if trial is None:
        raise KeyError(f"试验 {trial_id} 不存在")

    plots = session.scalars(
        select(TrialPlot).where(TrialPlot.trial_id == trial_id)
    ).all()
    obs_rows = session.scalars(
        select(TraitObservation)
        .join(TrialPlot, TraitObservation.plot_id == TrialPlot.id)
        .where(TrialPlot.trial_id == trial_id, TraitObservation.trait == trait)
    ).all()

    obs_by_plot: dict[int, list[TraitObservation]] = defaultdict(list)
    for obs in obs_rows:
        obs_by_plot[obs.plot_id].append(obs)

    events = {e.id: e for e in session.scalars(select(MatingEvent)).all()}
    rev_map = confirmed_revision_map(session)
    germ = {g.id: g for g in session.scalars(select(Germplasm)).all()}

    def family_label(pair: tuple[int | None, int | None]) -> str:
        female_id, male_id = pair
        female = germ.get(female_id)
        male = germ.get(male_id)
        if female_id is not None and female_id == male_id:
            return f"{female.name}({female.code}) 自交"
        female_txt = f"{female.name}({female.code})" if female else "未知母本"
        male_txt = f"{male.name}({male.code})" if male else "未知父本"
        return f"{female_txt} × {male_txt}"

    # 家系 = 现行亲本组合；同一组合的不同交配事件合并为一个家系
    families: dict[tuple, dict] = {}
    for plot in plots:
        if plot.family_id is None:
            continue
        event = events[plot.family_id]
        pair = effective_parents(session, event, rev_map)
        fam = families.setdefault(
            pair,
            {
                "event_codes": [],
                "family_label": family_label(pair),
                "plots": [],
            },
        )
        if event.code not in fam["event_codes"]:
            fam["event_codes"].append(event.code)

        # 株内归并
        by_plant: dict[str, list[TraitObservation]] = defaultdict(list)
        for obs in obs_by_plot.get(plot.id, []):
            by_plant[obs.plant_tag].append(obs)

        plant_values, n_missing, n_dead, n_zero = [], 0, 0, 0
        for plant_obs in by_plant.values():
            state, value = _plant_outcome(plant_obs)
            if state == "measured":
                plant_values.append(value)
                if value == 0.0:
                    n_zero += 1
            elif state == "dead":
                n_dead += 1
            else:
                n_missing += 1

        fam["plots"].append(
            {
                "plot_label": plot.label,
                "replicate": plot.replicate,
                "mean": mean(plant_values) if plant_values else None,
                "n_plants_measured": len(plant_values),
                "n_missing": n_missing,
                "n_dead": n_dead,
                "n_true_zero": n_zero,
            }
        )

    result = []
    for fam in families.values():
        plot_means = [p["mean"] for p in fam["plots"] if p["mean"] is not None]
        rep_groups: dict[int, list[float]] = defaultdict(list)
        for p in fam["plots"]:
            if p["mean"] is not None:
                rep_groups[p["replicate"]].append(p["mean"])
        replicates = [
            {"replicate": rep, "mean": mean(vals), "n_plots": len(vals)}
            for rep, vals in sorted(rep_groups.items())
        ]
        event_codes = sorted(fam["event_codes"])
        result.append(
            {
                "family_code": event_codes[0],  # 代表事件（兼容旧前端）
                "event_codes": event_codes,
                "family_label": fam["family_label"],
                "mean": mean(plot_means) if plot_means else None,
                "n_replicates": len(replicates),
                "n_plots": len(fam["plots"]),
                "n_plants_measured": sum(
                    p["n_plants_measured"] for p in fam["plots"]
                ),
                "n_missing": sum(p["n_missing"] for p in fam["plots"]),
                "n_dead": sum(p["n_dead"] for p in fam["plots"]),
                "n_true_zero": sum(p["n_true_zero"] for p in fam["plots"]),
                "replicates": replicates,
                "plots": sorted(
                    fam["plots"], key=lambda p: (p["replicate"], p["plot_label"])
                ),
            }
        )

    result.sort(key=lambda f: (f["mean"] is None, -(f["mean"] or 0)))
    return {
        "trial": {"id": trial.id, "name": trial.name, "season": trial.season},
        "trait": trait,
        "families": result,
    }


def create_recalc_proposals(
    session: Session, revision
) -> list[RecalcProposal]:
    """修订生效后，为受影响的 (试验, 性状) 形成“待确认的重算”。

    只针对已有发布版本的 (试验, 性状)；未发布过的组合无需保护，
    实时统计自然按新分组计算。
    """
    event = revision.mating_event
    plots = session.scalars(
        select(TrialPlot).where(TrialPlot.family_id == event.id)
    ).all()
    made: list[RecalcProposal] = []
    for trial_id in sorted({p.trial_id for p in plots}):
        plot_ids = [p.id for p in plots if p.trial_id == trial_id]
        traits = session.scalars(
            select(TraitObservation.trait)
            .where(TraitObservation.plot_id.in_(plot_ids))
            .distinct()
        ).all()
        for trait in traits:
            pub = session.scalars(
                select(PublishedResult)
                .where(
                    PublishedResult.trial_id == trial_id,
                    PublishedResult.trait == trait,
                )
                .order_by(PublishedResult.version.desc())
            ).first()
            if pub is None:
                continue
            proposal = RecalcProposal(
                code=next_code(session, RecalcProposal, "RC"),
                trial_id=trial_id,
                trait=trait,
                based_version=pub.version,
                revision_id=revision.id,
                payload=family_stats(session, trial_id, trait),
            )
            session.add(proposal)
            session.flush()
            made.append(proposal)
    return made
