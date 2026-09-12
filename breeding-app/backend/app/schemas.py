"""API 入参/出参模型。"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from .models import MatingType, ObsStatus


class GermplasmCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    generation: int = Field(default=0, ge=0)
    notes: str = ""


class MatingCreate(BaseModel):
    """登记交配事件；可同时登记新后代（按名称）或挂接已有材料（按编号）。"""

    type: MatingType
    female_code: str
    male_code: str | None = None  # None = 父本未知，不伪造
    season: str = ""
    notes: str = ""
    offspring_names: list[str] = []
    offspring_codes: list[str] = []  # 挂接已存在的材料（如补录历史谱系）


class TrialCreate(BaseModel):
    name: str = Field(min_length=1)
    season: str = ""


class PlotCreate(BaseModel):
    label: str
    replicate: int = Field(default=1, ge=1)
    family_code: str | None = None  # 交配事件编号


class ObservationCreate(BaseModel):
    plot_id: int
    plant_tag: str = Field(min_length=1)
    germplasm_code: str | None = None  # None = 标签丢失，身份未知
    trait: str = Field(min_length=1)
    status: ObsStatus
    value: float | None = None
    observed_on: date | None = None
    source: str = ""

    @model_validator(mode="after")
    def check_value_status(self):
        if self.status == ObsStatus.MEASURED and self.value is None:
            raise ValueError("已测（MEASURED）观测必须给出数值；真实零值请填 0")
        if self.status in (ObsStatus.MISSING, ObsStatus.DEAD) and self.value is not None:
            raise ValueError("未测/死亡观测不能带数值；请区分未测、死亡与真实零值")
        return self


class ObservationUpdate(BaseModel):
    """补录/更正。规则：
    - MISSING → MEASURED：补录，必须给 value；
    - MISSING → DEAD：允许（后发现死亡）；
    - MEASURED → MEASURED：更正数值，必须注明 source；
    - DEAD 记录不可改为已测（死亡植株不会再有测定值）。
    """

    status: ObsStatus
    value: float | None = None
    source: str = Field(min_length=1)  # 任何修改都必须留来源

    @model_validator(mode="after")
    def check_value_status(self):
        if self.status == ObsStatus.MEASURED and self.value is None:
            raise ValueError("补录为已测必须给出数值；真实零值请填 0")
        if self.status in (ObsStatus.MISSING, ObsStatus.DEAD) and self.value is not None:
            raise ValueError("未测/死亡观测不能带数值")
        return self
