"""
工作評分使用的 Pydantic 模型：偏好檔（Preferences）、AI 輸出（AIAssessment）與評分結果（JobScore）。

中文鍵名一律以 alias 定義，屬性名稱使用英文，方便程式存取。
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 評分維度，順序即輸出、未知維度清單的排列順序
CAREER_FIT = "職涯方向契合度"
SKILL_MATCH = "技能匹配度"
INDUSTRY_FIT = "產業公司吸引力"
SALARY = "薪資水準"
DIMENSIONS = (CAREER_FIT, SKILL_MATCH, INDUSTRY_FIT, SALARY)


# ---------------------------------------------------------------------------
# 偏好檔（preferences.yaml）
# ---------------------------------------------------------------------------

class _ProfileModel(BaseModel):
    """偏好檔模型的共同設定：嚴格型別、不接受未定義的欄位、所有欄位必填"""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class IndustryPreference(_ProfileModel):
    liked: list[str] = Field(alias="喜歡")
    disliked: list[str] = Field(alias="不喜歡")


class SalaryPreference(_ProfileModel):
    expected: int = Field(alias="期望月薪", gt=0)
    minimum: int = Field(alias="底線月薪", gt=0)
    annual_months: int = Field(alias="年薪換算月數", gt=0)

    @model_validator(mode="after")
    def _check_minimum(self) -> Self:
        """
        確認底線月薪不高於期望月薪

        :return: SalaryPreference, 通過驗證的自身
        """
        if self.minimum > self.expected:
            raise ValueError(f"底線月薪 {self.minimum} 不可大於期望月薪 {self.expected}")
        return self


class EliminationRules(_ProfileModel):
    companies: list[str] = Field(alias="公司")
    title_keywords: list[str] = Field(alias="職稱關鍵字")

    @model_validator(mode="after")
    def _check_title_keywords(self) -> Self:
        """
        確認職稱關鍵字沒有空字串（空字串會命中所有職稱，淘汰全部職缺）

        :return: EliminationRules, 通過驗證的自身
        """
        if any(not k.strip() for k in self.title_keywords):
            raise ValueError("職稱關鍵字不可為空字串")
        return self


class Preferences(_ProfileModel):
    goals: list[str] = Field(alias="目標方向")
    industry: IndustryPreference = Field(alias="產業偏好")
    salary: SalaryPreference = Field(alias="薪資")
    elimination: EliminationRules = Field(alias="淘汰條件")
    weights: dict[str, float] = Field(alias="權重")

    @model_validator(mode="after")
    def _check_weights(self) -> Self:
        """
        確認權重的鍵剛好是四個評分維度，值都 ≥ 0，且總和 > 0

        :return: Preferences, 通過驗證的自身
        """
        keys = set(self.weights)
        if keys != set(DIMENSIONS):
            missing = [d for d in DIMENSIONS if d not in keys]
            unknown = sorted(keys - set(DIMENSIONS))
            raise ValueError(f"權重的鍵必須剛好是 {list(DIMENSIONS)}；缺少 {missing}，多出 {unknown}")
        negative = [k for k, v in self.weights.items() if v < 0]
        if negative:
            raise ValueError(f"權重不可為負數：{negative}")
        if sum(self.weights.values()) <= 0:
            raise ValueError("權重總和必須大於 0")
        return self


# ---------------------------------------------------------------------------
# AI 輸出：英文欄位名，讓各家模型的 schema 較穩定
# ---------------------------------------------------------------------------

class AIDimension(BaseModel):
    score: int | None = Field(ge=1, le=5, description="1–5 的整數；資訊不足時為 null")
    reason: str = Field(description="評分理由，需具體引用職缺內容")


class AIAssessment(BaseModel):
    career_fit: AIDimension = Field(description="職涯方向契合度")
    skill_match: AIDimension = Field(description="技能匹配度")
    industry_fit: AIDimension = Field(description="產業公司吸引力")
    comment: str = Field(description="一到兩句總評")


# ---------------------------------------------------------------------------
# 評分結果
# ---------------------------------------------------------------------------

# 只在輸出時使用中文鍵名（serialization_alias），建構時使用英文屬性名稱

class DimensionScore(BaseModel):
    score: int | None = Field(serialization_alias="分數")
    reason: str = Field(serialization_alias="理由")


class JobScore(BaseModel):
    job_no: str = Field(serialization_alias="職缺代碼")
    eliminated: bool = Field(serialization_alias="淘汰")
    elimination_reasons: list[str] = Field(serialization_alias="淘汰原因")
    dimensions: dict[str, DimensionScore] | None = Field(serialization_alias="維度")
    total: int | None = Field(serialization_alias="總分")
    unknown_dimensions: list[str] = Field(serialization_alias="未知維度")
    comment: str = Field(serialization_alias="評語")


class BatchResult(BaseModel):
    """整批評分中的一筆結果：評分結果加上從職缺帶入的欄位與失敗原因；欄位順序即輸出順序"""

    job_no: str = Field(serialization_alias="職缺代碼")
    job_name: str | None = Field(serialization_alias="職缺名稱")
    company: str | None = Field(serialization_alias="公司名稱")
    salary_text: str | None = Field(serialization_alias="薪資待遇")
    job_url: str | None = Field(serialization_alias="職缺連結")
    eliminated: bool = Field(serialization_alias="淘汰")
    elimination_reasons: list[str] = Field(serialization_alias="淘汰原因")
    dimensions: dict[str, DimensionScore] | None = Field(serialization_alias="維度")
    total: int | None = Field(serialization_alias="總分")
    unknown_dimensions: list[str] = Field(serialization_alias="未知維度")
    comment: str | None = Field(serialization_alias="評語")
    failure: str | None = Field(serialization_alias="失敗原因")
    # 是否沿用上次的 AI 評分，只供摘要統計，不輸出到結果檔
    reused: bool = Field(exclude=True)
