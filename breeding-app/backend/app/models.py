"""数据模型：材料身份、交配事件、试验小区、性状观测。

设计要点：
- Germplasm.code 是稳定编号（GM-0001…），全局唯一；name 不唯一，
  同名材料只能靠 code 区分。
- 自交（SELF）与杂交（CROSS）分开建模：SELF 的父本=母本；
  CROSS 要求父母本不同，父本可未知（NULL，绝不伪造占位材料）。
- 每个材料最多有一个来源交配事件（Progeny.germplasm_id 唯一）。
- 观测区分 MEASURED / MISSING（未测）/ DEAD（死亡）；
  真实零值是 MEASURED 且 value=0.0，与 MISSING 完全不同。
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MatingType(str, enum.Enum):
    CROSS = "CROSS"  # 杂交：两个不同亲本，父本可未知
    SELF = "SELF"    # 自交：同一亲本


class ObsStatus(str, enum.Enum):
    MEASURED = "MEASURED"  # 已测（value 必填，0.0 是真实零值）
    MISSING = "MISSING"    # 未测（value 必空）
    DEAD = "DEAD"          # 植株死亡（value 必空）


class ParentField(str, enum.Enum):
    FEMALE = "FEMALE"
    MALE = "MALE"


class RevisionStatus(str, enum.Enum):
    DRAFT = "DRAFT"          # 草案：不影响任何结论
    CONFIRMED = "CONFIRMED"  # 已确认生效（有证据与确认人）
    REJECTED = "REJECTED"    # 已驳回
    SUPERSEDED = "SUPERSEDED"  # 被后续修订取代（保留历史）


class RecalcStatus(str, enum.Enum):
    PENDING = "PENDING"      # 待确认的重算
    APPROVED = "APPROVED"    # 已批准 → 形成新发布版本
    REJECTED = "REJECTED"    # 已驳回 → 旧发布版本继续有效


class DecisionType(str, enum.Enum):
    KEPT = "KEPT"      # 保留（人工决定）
    CULLED = "CULLED"  # 淘汰（人工决定）


class Germplasm(Base):
    __tablename__ = "germplasm"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)  # 允许重名
    generation: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatingEvent(Base):
    __tablename__ = "mating_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    type: Mapped[MatingType] = mapped_column(
        Enum(MatingType, native_enum=False, length=10)
    )
    female_parent_id: Mapped[int] = mapped_column(ForeignKey("germplasm.id"))
    # NULL = 父本未知（如混合花粉、标签丢失），不伪造补全
    male_parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("germplasm.id"), nullable=True
    )
    season: Mapped[str] = mapped_column(String(40), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    female_parent: Mapped[Germplasm] = relationship(
        foreign_keys=[female_parent_id]
    )
    male_parent: Mapped[Germplasm | None] = relationship(
        foreign_keys=[male_parent_id]
    )
    progeny_links: Mapped[list["Progeny"]] = relationship(
        back_populates="mating_event", cascade="all, delete-orphan"
    )


class Progeny(Base):
    """交配事件 → 后代的连接。每个材料至多一个来源事件。"""

    __tablename__ = "progeny"
    __table_args__ = (
        UniqueConstraint("mating_event_id", "germplasm_id", name="uq_event_child"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mating_event_id: Mapped[int] = mapped_column(ForeignKey("mating_event.id"))
    germplasm_id: Mapped[int] = mapped_column(
        ForeignKey("germplasm.id"), unique=True
    )

    mating_event: Mapped[MatingEvent] = relationship(back_populates="progeny_links")
    germplasm: Mapped[Germplasm] = relationship()


class Trial(Base):
    __tablename__ = "trial"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    season: Mapped[str] = mapped_column(String(40), default="")

    plots: Mapped[list["TrialPlot"]] = relationship(
        back_populates="trial", cascade="all, delete-orphan"
    )


class TrialPlot(Base):
    """试验小区：属于某试验、某重复，种植某个家系（交配事件的后代）。"""

    __tablename__ = "trial_plot"
    __table_args__ = (
        UniqueConstraint("trial_id", "label", name="uq_trial_plot_label"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trial.id"))
    label: Mapped[str] = mapped_column(String(40))
    replicate: Mapped[int] = mapped_column(Integer, default=1)
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("mating_event.id"), nullable=True
    )

    trial: Mapped[Trial] = relationship(back_populates="plots")
    family: Mapped[MatingEvent | None] = relationship()


class TraitObservation(Base):
    """性状观测。同一小区内同株（plant_tag）可有多条重复测定，
    统计时先在株内平均，不作为独立重复。
    germplasm_id 为 NULL 表示标签丢失、身份未知（不伪造归属）。
    """

    __tablename__ = "trait_observation"

    id: Mapped[int] = mapped_column(primary_key=True)
    plot_id: Mapped[int] = mapped_column(ForeignKey("trial_plot.id"))
    plant_tag: Mapped[str] = mapped_column(String(40))
    germplasm_id: Mapped[int | None] = mapped_column(
        ForeignKey("germplasm.id"), nullable=True
    )
    trait: Mapped[str] = mapped_column(String(60))
    status: Mapped[ObsStatus] = mapped_column(
        Enum(ObsStatus, native_enum=False, length=10)
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_on: Mapped[date] = mapped_column(Date, default=date.today)
    source: Mapped[str] = mapped_column(String(200), default="")  # 来源/录入人
    backfilled: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否补录
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    plot: Mapped[TrialPlot] = relationship()
    germplasm: Mapped[Germplasm | None] = relationship()


class ParentageRevision(Base):
    """亲本修订。原交配事件永不被覆盖；确认生效的修订形成“现行亲本”。

    - 草案（DRAFT）不影响谱系与统计；
    - 确认需要证据与确认人（且确认人 ≠ 提出人）；
    - 同一事件的同一亲本字段，最多一个 CONFIRMED；
      新修订确认时旧修订转为 SUPERSEDED（保留历史）。
    """

    __tablename__ = "parentage_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    mating_event_id: Mapped[int] = mapped_column(ForeignKey("mating_event.id"))
    field: Mapped[ParentField] = mapped_column(
        Enum(ParentField, native_enum=False, length=10)
    )
    old_parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("germplasm.id"), nullable=True
    )  # 起草时的现行亲本（快照）
    new_parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("germplasm.id"), nullable=True
    )  # NULL = 修订为未知（仅当另一亲本已知才允许生效）
    evidence: Mapped[str] = mapped_column(Text, default="")   # 证据
    proposer: Mapped[str] = mapped_column(String(60), default="")   # 提出人
    confirmer: Mapped[str] = mapped_column(String(60), default="")  # 确认人
    status: Mapped[RevisionStatus] = mapped_column(
        Enum(RevisionStatus, native_enum=False, length=12),
        default=RevisionStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    mating_event: Mapped[MatingEvent] = relationship()
    old_parent: Mapped[Germplasm | None] = relationship(
        foreign_keys=[old_parent_id]
    )
    new_parent: Mapped[Germplasm | None] = relationship(
        foreign_keys=[new_parent_id]
    )


class PublishedResult(Base):
    """已发布的家系统计版本：不可变，按 (试验, 性状, 版本) 留存。"""

    __tablename__ = "published_result"
    __table_args__ = (
        UniqueConstraint("trial_id", "trait", "version", name="uq_pub_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trial.id"))
    trait: Mapped[str] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)  # 发布时的家系统计快照
    published_by: Mapped[str] = mapped_column(String(60), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RecalcProposal(Base):
    """待确认的重算：修订生效后自动形成，须人工批准才成为新发布版本。"""

    __tablename__ = "recalc_proposal"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trial.id"))
    trait: Mapped[str] = mapped_column(String(60))
    based_version: Mapped[int] = mapped_column(Integer)  # 基于哪个发布版本
    revision_id: Mapped[int] = mapped_column(ForeignKey("parentage_revision.id"))
    payload: Mapped[dict] = mapped_column(JSON)  # 新分组下的统计
    status: Mapped[RecalcStatus] = mapped_column(
        Enum(RecalcStatus, native_enum=False, length=10),
        default=RecalcStatus.PENDING,
    )
    resolver: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    revision: Mapped[ParentageRevision] = relationship()


class SelectionDecision(Base):
    """人工淘汰/保留决定。任何自动流程（修订、重算）都不得改动。"""

    __tablename__ = "selection_decision"

    id: Mapped[int] = mapped_column(primary_key=True)
    germplasm_id: Mapped[int] = mapped_column(
        ForeignKey("germplasm.id"), unique=True
    )
    decision: Mapped[DecisionType] = mapped_column(
        Enum(DecisionType, native_enum=False, length=10)
    )
    note: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(60), default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    germplasm: Mapped[Germplasm] = relationship()
