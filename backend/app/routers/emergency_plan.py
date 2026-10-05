"""应急预案演练台账接口：预案版本、演练记录、演练待办与导入记录。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, PageResult
from app.services.emergency_plan import service

router = APIRouter(prefix="/api/emergency-plan", tags=["应急预案演练台账"])


class PlanPayload(BaseModel):
    预案编号: str = ""
    预案名称: str = ""
    电站: str = ""


class VersionPayload(BaseModel):
    版本号: str = ""
    事故类别: list[str] = Field(default_factory=list)
    预案内容: str | None = None
    批复人: str | None = None
    发布日期: str | None = None

class Participant(BaseModel):
    姓名: str = ""
    岗位: str = ""


class Rectification(BaseModel):
    整改内容: str = ""
    责任人: str | None = None
    整改期限: str | None = None


class DrillPayload(BaseModel):
    plan_id: int
    version_id: int
    演练名称: str
    演练日期: str
    事故类别: str
    演练地点: str | None = None
    总指挥: str | None = None
    参演人员: list[Participant] = Field(default_factory=list)
    演练结论评级: str | None = None
    演练结论: str | None = None
    整改项: list[Rectification] = Field(default_factory=list)


class VersionActionPayload(BaseModel):
    action: str
    批复人: str | None = None
    发布日期: str | None = None


class TodoPayload(BaseModel):
    整改内容: str = ""
    责任人: str | None = None
    整改期限: str | None = None


class TodoActionPayload(BaseModel):
    action: str


class ImportPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "文档导入"
    operator: str = "值班管理员"


def _year_param(year: int | None) -> int:
    from datetime import date
    return year or date.today().year


def _version_values(payload: "VersionPayload") -> dict[str, Any]:
    """入参沿用页面中文口径（事故类别），服务层统一使用 accident_types。"""
    values = payload.model_dump(exclude_none=True)
    types = values.pop("事故类别", None)
    if types is not None:
        values["accident_types"] = types
    return values


# ---------- 元数据与看板 ----------
@router.get("/meta")
def get_meta() -> dict[str, Any]:
    """事故类别目录、结论评级与状态枚举，前端下拉统一从这里取。"""
    return service.meta()


@router.get("/stats")
def get_stats(year: int | None = Query(default=None, description="统计年份，默认当前年")) -> dict[str, Any]:
    """台账看板：预案数、现行版本平均覆盖率、年度演练场次、待整改与逾期。"""
    return service.stats(_year_param(year))


# ---------- 预案 ----------
@router.get("", response_model=PageResult[dict])
def list_plans(
    keyword: str | None = Query(default=None, description="按预案编号或名称检索"),
    station: str | None = Query(default=None, description="按电站筛选"),
    year: int | None = Query(default=None, description="覆盖率统计年份，默认当前年"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """预案台账列表，每行挂当前版本与本年度覆盖率。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_plans(
        keyword=keyword, station=station, year=_year_param(year), page=page, size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("", response_model=ActionResult)
def create_plan(payload: PlanPayload) -> ActionResult:
    """登记预案主档（编号 + 名称 + 电站），随后需建立并批复版本。"""
    entry, missing = service.create_plan(payload.model_dump())
    if missing:
        return ActionResult(ok=False, message=missing[0] if len(missing) == 1 else f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="预案主档已登记，请建立首版草稿", entry=entry)


# ---------- 版本 ----------
@router.get("/versions/{version_id}")
def get_version(version_id: int) -> dict[str, Any]:
    """版本明细：已批复版本只读返回，包含挂在该版本下的历史演练与覆盖率。"""
    entry = service.get_version(version_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"版本 {version_id} 不存在")
    return entry


@router.post("/{plan_id}/versions", response_model=ActionResult)
def create_version(plan_id: int, payload: VersionPayload) -> ActionResult:
    """基于现行版本新建一版草稿；改一版存一版，已批复版本不受影响。"""
    entry, message = service.create_version(plan_id, _version_values(payload))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/versions/{version_id}", response_model=ActionResult)
def update_version(version_id: int, payload: VersionPayload) -> ActionResult:
    """仅草稿可编辑；已批复版本走到这里会被拦下，不允许就地修改。"""
    entry, message = service.update_version(version_id, _version_values(payload))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/versions/{version_id}/actions", response_model=ActionResult)
def run_version_action(version_id: int, payload: VersionActionPayload) -> ActionResult:
    """版本流转：提交批复、撤回批复、批复。批复需带批复人，可带发布日期；批复后成为唯一现行版本。"""
    values = payload.model_dump(exclude_none=True)
    action = values.pop("action")
    entry, message = service.run_version_action(version_id, action, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.delete("/versions/{version_id}", response_model=ActionResult)
def discard_version(version_id: int) -> ActionResult:
    """作废在途草稿/待批复版本；已批复版本作为台账凭证不允许删除。"""
    ok, message = service.discard_version(version_id)
    return ActionResult(ok=ok, message=message)


# ---------- 演练记录 ----------
@router.get("/drills", response_model=PageResult[dict])
def list_drills(
    plan_id: int | None = None,
    version_id: int | None = None,
    year: int | None = None,
    keyword: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """演练记录列表；可按预案、版本、年份过滤，历史演练随原版本口径保留。"""
    items, total = service.list_drills(
        plan_id=plan_id, version_id=version_id, year=year,
        keyword=keyword, page=page, size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/drills", response_model=ActionResult)
def create_drill(payload: DrillPayload) -> ActionResult:
    """登记一场演练：参演人员逐条录入，整改项自动落成演练待办。"""
    entry, message = service.create_drill(payload.model_dump())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/drills/{drill_id}")
def get_drill(drill_id: int) -> dict[str, Any]:
    entry = service.get_drill(drill_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"演练记录 {drill_id} 不存在")
    return entry


# ---------- 演练待办 ----------
@router.get("/todos", response_model=PageResult[dict])
def list_todos(
    status: str | None = None,
    drill_id: int | None = None,
    page: int = 1,
    size: int = 50,
) -> PageResult[dict]:
    """整改待办台账：默认按未闭环优先、整改期限升序。"""
    items, total = service.list_todos(status=status, drill_id=drill_id, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/drills/{drill_id}/todos", response_model=ActionResult)
def add_todo(drill_id: int, payload: TodoPayload) -> ActionResult:
    """给已登记演练追加整改项。"""
    entry, message = service.add_todo(drill_id, payload.model_dump())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/todos/{todo_id}/actions", response_model=ActionResult)
def run_todo_action(todo_id: int, payload: TodoActionPayload) -> ActionResult:
    """待办流转：认领整改、完成闭环。"""
    entry, message = service.run_todo_action(todo_id, payload.action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


# ---------- 导入 ----------
@router.post("/imports", response_model=ActionResult)
def import_plans(payload: ImportPayload) -> ActionResult:
    """批量导入预案版本：同一份预案只留一条，每次导入落库一条导入记录。"""
    log, message = service.import_plans(
        items=payload.items, source=payload.source, operator=payload.operator,
    )
    return ActionResult(ok=True, message=message, entry=log)


@router.get("/imports", response_model=PageResult[dict])
def list_imports(page: int = 1, size: int = 20) -> PageResult[dict]:
    """导入记录列表，含每行新增/重复跳过/失败的明细。"""
    items, total = service.list_import_logs(page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/imports/{log_id}")
def get_import(log_id: int) -> dict[str, Any]:
    entry = service.get_import_log(log_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"导入记录 {log_id} 不存在")
    return entry


# ---------- 预案详情（动态路由最后注册，避免吞掉 /drills、/todos、/imports） ----------
@router.get("/{plan_id}")
def get_plan(
    plan_id: int,
    year: int | None = Query(default=None, description="覆盖率统计年份，默认当前年"),
) -> dict[str, Any]:
    """预案详情：现行版本、全部历史版本、挂在各版本下的演练，覆盖率按版本分别给出。"""
    entry = service.get_plan(plan_id, _year_param(year))
    if entry is None:
        raise HTTPException(status_code=404, detail=f"预案 {plan_id} 不存在")
    return entry
