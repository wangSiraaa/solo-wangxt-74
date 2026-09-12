"""家系统计：按“小区 × 重复”口径聚合。

口径约定（与育种田间试验一致）：
1. 株为最小观测单位：同株多次测定先在株内平均，不作为独立重复；
2. 小区均值为该小区内全部“已测株”的株均值之平均；
3. 家系均值为各小区均值之平均（小区是试验单位，不按株数加权）；
4. 未测（MISSING）与死亡（DEAD）不进入均值，只分别计数；
   真实零值（MEASURED 且 value=0.0）正常进入均值并单独计数；
5. 株状态判定：任一观测为 DEAD ⇒ 死亡；否则任一 MEASURED ⇒ 已测；
   否则为未测。
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    MatingEvent,
    ObsStatus,
    TraitObservation,
    Trial,
    TrialPlot,
)


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

    events = {
        e.id: e
        for e in session.scalars(select(MatingEvent)).all()
    }

    def family_label(event: MatingEvent) -> str:
        female = event.female_parent
        male = event.male_parent
        if event.type.value == "SELF":
            cross = f"{female.name}({female.code}) 自交"
        else:
            male_txt = (
                f"{male.name}({male.code})" if male is not None else "未知父本"
            )
            cross = f"{female.name}({female.code}) × {male_txt}"
        return f"{event.code}: {cross}"

    families: dict[int, dict] = {}
    for plot in plots:
        if plot.family_id is None:
            continue
        fam = families.setdefault(
            plot.family_id,
            {
                "family_code": events[plot.family_id].code,
                "family_label": family_label(events[plot.family_id]),
                "plots": [],
            },
        )

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
        result.append(
            {
                "family_code": fam["family_code"],
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
