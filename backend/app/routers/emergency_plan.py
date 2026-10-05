"""应急预案演练台账接口。

覆盖四件事：
1. 预案建档与版本管理（草稿/待批复/已批复/已归档，已批复版本不可变）；
2. 演练记录登记（参演人员、日期、结论逐条录入）与整改待办流转；
3. 当前版本演练覆盖率看板（换版后按新版本重算）；
4. 预案导入（重复去重、导入记录落库、存量按发布日期回填）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    DrillPayload,
    PageResult,
    PlanImportPayload,
    PlanPayload,
    PlanVersionPayload,
    RectificationActionPayload,
    RectificationPayload,
    VersionActionPayload,
)
from app.services.emergency_plan import service

router = APIRouter(prefix="/api/emergency-plans", tags=["应急预案演练台账"])

# 注意：字面量路径（coverage/drills/rectifications/imports）必须声明在
# /{plan_id} 之前，否则会被参数路径抢先匹配。


# ------------------------------------------------------------------ 覆盖率
@router.get("/coverage")
def coverage_board() -> dict:
    """覆盖率看板：按各预案当前版本重算今年演练覆盖的事故类别占比。"""
    return service.coverage_board()


# ---------------------------------------------------------------------- 演练
@router.get("/drills/list", response_model=PageResult[dict])
def list_drills(
    plan_id: int | None = None,
    version_id: int | None = None,
    year: int | None = Query(default=None, description="按演练年份过滤，如 2026"),
    accident_type: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """演练记录列表，支持按预案、版本、年份、事故类别筛选。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_drills(
        plan_id=plan_id, version_id=version_id, year=year,
        accident_type=accident_type, page=page, size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/drills", response_model=ActionResult)
def create_drill(payload: DrillPayload) -> ActionResult:
    """登记演练：参演人员、日期、结论逐条录入，并校验版本与事故类别口径。"""
    entry, message = service.create_drill(payload.model_dump())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/drills/{drill_id}", response_model=dict)
def get_drill(drill_id: int) -> dict:
    """演练详情：含该次演练挂出的整改项。"""
    drill = service.get_drill(drill_id)
    if drill is None:
        raise HTTPException(status_code=404, detail=f"演练记录 {drill_id} 不存在")
    return drill


@router.post("/drills/{drill_id}/rectifications", response_model=ActionResult)
def add_rectification(drill_id: int, payload: RectificationPayload) -> ActionResult:
    """演练发现的问题落到演练待办。"""
    entry, message = service.add_rectification(drill_id, payload.model_dump())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


# ------------------------------------------------------------------ 整改待办
@router.get("/rectifications")
def list_rectifications(status: str | None = None, assignee: str | None = None) -> dict:
    """演练整改待办：默认未闭环在前，可按状态、责任人筛选。"""
    return {"items": service.list_rectifications(status=status, assignee=assignee)}


@router.post("/rectifications/{rect_id}/actions", response_model=ActionResult)
def run_rectification_action(rect_id: int, payload: RectificationActionPayload) -> ActionResult:
    """开始整改 / 闭环验证。"""
    action = (payload.action or "").strip()
    entry, message = service.run_rectification_action(rect_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


# ---------------------------------------------------------------------- 导入
@router.post("/imports", response_model=ActionResult)
def import_plans(payload: PlanImportPayload) -> ActionResult:
    """导入预案版本：同一预案+版本号重复只留一条，批次与逐行结果落库。"""
    batch, message = service.import_plans(
        payload.rows,
        import_type=payload.import_type,
        operator=payload.operator or "",
        remark=payload.remark or "",
    )
    if batch is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(
        ok=True,
        message=f"导入完成：新增 {batch['created_count']} 条，重复 {batch['duplicated_count']} 条",
        entry=batch,
    )


@router.get("/imports/list")
def list_imports() -> dict:
    """导入记录：每次导入（含存量回填）都在这里留痕。"""
    return {"items": service.list_imports()}


# ---------------------------------------------------------------------- 预案
@router.get("", response_model=PageResult[dict])
def list_plans(
    keyword: str | None = Query(default=None, description="按预案编号或名称检索"),
    station: str | None = None,
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """预案台账列表：每条带出当前版本号与按当前版本计算的今年覆盖率。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_plans(keyword=keyword, station=station, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("", response_model=ActionResult)
def create_plan(payload: PlanPayload) -> ActionResult:
    """建立预案档案（不含任何版本），编号重复时拦下。"""
    entry, missing = service.create_plan(payload.model_dump())
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段或编号冲突：{'、'.join(missing)}")
    return ActionResult(ok=True, message="预案档案已建立", entry=entry)


@router.get("/{plan_id}", response_model=dict)
def get_plan(plan_id: int) -> dict:
    """预案详情：版本时间线 + 今年演练数 + 待整改数，所有页面共用同一口径。"""
    plan = service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"预案 {plan_id} 不存在")
    return plan


# ---------------------------------------------------------------------- 版本
@router.get("/{plan_id}/versions")
def list_versions(plan_id: int) -> dict:
    """版本列表：已归档、已批复与在途版本一并展示。"""
    if service.get_plan(plan_id) is None:
        raise HTTPException(status_code=404, detail=f"预案 {plan_id} 不存在")
    return {"plan_id": plan_id, "items": service.list_versions(plan_id)}


@router.post("/{plan_id}/versions", response_model=ActionResult)
def create_version(plan_id: int, payload: PlanVersionPayload) -> ActionResult:
    """改一版存一版：新建草稿版本，已批复旧版保持不动。"""
    entry, message = service.create_version(plan_id, payload.model_dump())
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"草稿版本 {entry['version_no']} 已建立", entry=entry)


@router.put("/versions/{version_id}", response_model=ActionResult)
def update_version(version_id: int, payload: PlanVersionPayload) -> ActionResult:
    """就地修改仅限草稿；已批复版本不可改，接口直接拒绝。"""
    entry, message = service.update_version(version_id, payload.model_dump(exclude_unset=True))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="草稿版本已更新", entry=entry)


@router.post("/versions/{version_id}/actions", response_model=ActionResult)
def run_version_action(version_id: int, payload: VersionActionPayload) -> ActionResult:
    """提交批复 / 批复通过 / 批复驳回。批复通过时切换当前版本指针并归档旧版。"""
    action = (payload.action or "").strip()
    entry, message = service.run_version_action(version_id, action, operator=payload.operator or "")
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
