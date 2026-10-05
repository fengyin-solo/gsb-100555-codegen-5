"""应急预案演练台账业务规则。

五张表围绕"预案 → 版本 → 演练 → 整改项"组织，另加一张导入批次表：

- 版本只增不改：已批复/已归档的版本即冻结（immutable=True），任何修改都会被拦下，
  换版只能在草稿上重新走一遍；
- 当前版本由预案主表上的 current_version_id 唯一定位，所有页面共用这一指针；
- 演练记录挂死在当时的 version_id 上，换版后历史演练仍按旧版本的事故类别口径归档；
- 覆盖率永远按"当前版本的事故类别 + 挂在当前版本且发生在今年的演练"实时重算。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

PLAN_TABLE = "ep_plans"
VERSION_TABLE = "ep_plan_versions"
DRILL_TABLE = "ep_drills"
RECTIFICATION_TABLE = "ep_drill_rectifications"
IMPORT_TABLE = "ep_imports"

DRAFT, PENDING, APPROVED, ARCHIVED = "草稿", "待批复", "已批复", "已归档"
VERSION_STATUSES = [DRAFT, PENDING, APPROVED, ARCHIVED]
IMMUTABLE_STATUSES = {APPROVED, ARCHIVED}

RECT_STATUSES = ["待整改", "整改中", "已闭环"]

PLAN_REQUIRED = ["plan_code", "plan_name", "station"]
VERSION_REQUIRED = ["version_no", "accident_types", "content_summary"]
DRILL_REQUIRED = ["version_id", "drill_no", "drill_date", "accident_type", "conclusion"]

ACTION_VERSION_RULES = {"提交批复": PENDING, "批复通过": APPROVED, "批复驳回": DRAFT}
ACTION_RECT_RULES = {"开始整改": "整改中", "闭环验证": "已闭环"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _rows(table: str) -> list[dict[str, Any]]:
    return store.rows(table)


def _next_id(table: str) -> int:
    return max((int(row.get("id", 0)) for row in _rows(table)), default=0) + 1


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _as_type_list(value: Any) -> list[str]:
    """事故类别允许传单值、逗号分隔字符串或列表，统一去空白去重保序。"""
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace("，", ",").split(",")
    result: list[str] = []
    for item in raw:
        text = _clean_text(item)
        if text and text not in result:
            result.append(text)
    return result


class EmergencyPlanService:
    # ------------------------------------------------------------------ 预案
    def list_plans(
        self,
        *,
        keyword: str | None = None,
        station: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(_rows(PLAN_TABLE))
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("plan_code", "")) or keyword in str(row.get("plan_name", ""))
            ]
        if station:
            rows = [row for row in rows if row.get("station") == station]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._plan_summary(row) for row in rows[start:start + size]], total

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        plan = store.find(PLAN_TABLE, plan_id)
        if plan is None:
            return None
        summary = self._plan_summary(plan)
        versions = [
            self._version_view(row)
            for row in _rows(VERSION_TABLE)
            if int(row.get("plan_id", 0)) == plan_id
        ]
        versions.sort(key=lambda row: (row["publish_date"] or "9999", row["id"]), reverse=True)
        summary["versions"] = versions
        summary["drills_this_year"] = sum(1 for d in self._plan_drills(plan_id) if self._is_this_year(d))
        summary["drills_total"] = len(self._plan_drills(plan_id))
        summary["rectifications_open"] = sum(
            1 for row in _rows(RECTIFICATION_TABLE)
            if int(row.get("plan_id", 0)) == plan_id and row.get("status") != "已闭环"
        )
        return summary

    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in PLAN_REQUIRED if not _clean_text(values.get(field))]
        if missing:
            return None, missing
        plan_code = _clean_text(values.get("plan_code"))
        if self._find_plan_by_code(plan_code) is not None:
            return None, [f"预案编号 {plan_code} 已存在，同一份预案请勿重复建立"]
        plan = {
            "id": _next_id(PLAN_TABLE),
            "plan_code": plan_code,
            "plan_name": _clean_text(values.get("plan_name")),
            "station": _clean_text(values.get("station")),
            "current_version_id": None,
            "created_at": _now(),
        }
        _rows(PLAN_TABLE).append(plan)
        return self._plan_summary(plan), []

    # ------------------------------------------------------------------ 版本
    def list_versions(self, plan_id: int) -> list[dict[str, Any]]:
        rows = [
            self._version_view(row)
            for row in _rows(VERSION_TABLE)
            if int(row.get("plan_id", 0)) == plan_id
        ]
        rows.sort(key=lambda row: row["id"])
        return rows

    def create_version(
        self, plan_id: int, values: dict[str, Any], *, source: str = "手工新建"
    ) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(PLAN_TABLE, plan_id)
        if plan is None:
            return None, f"预案 {plan_id} 不存在"
        types = _as_type_list(values.get("accident_types"))
        missing = [
            field for field in VERSION_REQUIRED
            if field == "accident_types" and not types
            or field != "accident_types" and not _clean_text(values.get(field))
        ]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        version_no = _clean_text(values.get("version_no"))
        if self._find_version(plan_id, version_no) is not None:
            return None, f"版本号 {version_no} 已存在，改一版请使用新的版本号"
        version = {
            "id": _next_id(VERSION_TABLE),
            "plan_id": plan_id,
            "version_no": version_no,
            "status": DRAFT,
            "accident_types": types,
            "publish_date": _clean_text(values.get("publish_date")),
            "approved_by": "",
            "content_summary": _clean_text(values.get("content_summary")),
            "source": source,
            "immutable": False,
            "created_at": _now(),
        }
        _rows(VERSION_TABLE).append(version)
        return self._version_view(version), ""

    def update_version(
        self, version_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """只允许就地修改草稿；已批复版本必须留痕，所以一律拒绝。"""
        version = store.find(VERSION_TABLE, version_id)
        if version is None:
            return None, f"预案版本 {version_id} 不存在"
        if version.get("status") != DRAFT:
            return None, (
                f"版本 {version.get('version_no')} 状态为「{version.get('status')}」，"
                "不允许就地修改，请基于当前版本新建一版"
            )
        if "accident_types" in values:
            version["accident_types"] = _as_type_list(values.get("accident_types"))
        for field in ("version_no", "publish_date", "content_summary"):
            if field in values:
                version[field] = _clean_text(values.get(field))
        return self._version_view(version), ""

    def run_version_action(
        self, version_id: int, action: str, *, operator: str = ""
    ) -> tuple[dict[str, Any] | None, str]:
        version = store.find(VERSION_TABLE, version_id)
        if version is None:
            return None, f"预案版本 {version_id} 不存在"
        target = ACTION_VERSION_RULES.get(action)
        if target is None:
            return None, f"动作「{action}」不属于预案版本可执行范围"
        status = version.get("status")
        if action == "提交批复" and status != DRAFT:
            return None, "只有草稿可以提交批复"
        if action == "批复驳回" and status != PENDING:
            return None, "只有待批复版本可以驳回"
        if action == "批复通过" and status != PENDING:
            return None, "只有待批复版本可以批复通过"

        if target == APPROVED:
            plan = store.find(PLAN_TABLE, int(version["plan_id"]))
            if plan is None:
                return None, f"预案 {version.get('plan_id')} 不存在"
            # 冻结新版本：旧的已批复版本归档留痕，指针整体切到新版本。
            current_id = plan.get("current_version_id")
            if current_id:
                old = store.find(VERSION_TABLE, int(current_id))
                if old is not None:
                    old["status"] = ARCHIVED
                    old["immutable"] = True
            version["status"] = APPROVED
            version["immutable"] = True
            if not version.get("publish_date"):
                version["publish_date"] = datetime.now().strftime("%Y-%m-%d")
            version["approved_by"] = _clean_text(operator) or version.get("approved_by") or "安监部"
            plan["current_version_id"] = version["id"]
            return self._version_view(version), f"版本 {version['version_no']} 批复通过，旧版本已归档"

        version["status"] = target
        return self._version_view(version), f"版本已{action}"

    # ------------------------------------------------------------------ 演练
    def list_drills(
        self,
        *,
        plan_id: int | None = None,
        version_id: int | None = None,
        year: int | None = None,
        accident_type: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(_rows(DRILL_TABLE))
        if plan_id is not None:
            rows = [row for row in rows if int(row.get("plan_id", 0)) == plan_id]
        if version_id is not None:
            rows = [row for row in rows if int(row.get("version_id", 0)) == version_id]
        if year is not None:
            rows = [row for row in rows if str(row.get("drill_date", "")).startswith(str(year))]
        if accident_type:
            rows = [row for row in rows if row.get("accident_type") == accident_type]
        rows.sort(key=lambda row: str(row.get("drill_date", "")), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._drill_view(row) for row in rows[start:start + size]], total

    def get_drill(self, drill_id: int) -> dict[str, Any] | None:
        drill = store.find(DRILL_TABLE, drill_id)
        if drill is None:
            return None
        view = self._drill_view(drill)
        view["rectifications"] = [
            self._rect_view(row)
            for row in _rows(RECTIFICATION_TABLE)
            if int(row.get("drill_id", 0)) == drill_id
        ]
        return view

    def create_drill(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        for field in DRILL_REQUIRED:
            if not _clean_text(values.get(field)):
                return None, f"缺少必填字段：{field}"
        version = store.find(VERSION_TABLE, int(values["version_id"]))
        if version is None:
            return None, f"预案版本 {values.get('version_id')} 不存在"
        if version.get("status") not in IMMUTABLE_STATUSES:
            return None, "演练只能登记在已批复的预案版本上，请先完成批复"
        accident_type = _clean_text(values.get("accident_type"))
        if accident_type not in (version.get("accident_types") or []):
            return None, f"事故类别「{accident_type}」不在该版本预案范围内"
        drill_no = _clean_text(values.get("drill_no"))
        if any(_clean_text(row.get("drill_no")) == drill_no for row in _rows(DRILL_TABLE)):
            return None, f"演练编号 {drill_no} 已存在"
        participants = values.get("participants")
        if not isinstance(participants, list) or not participants:
            return None, "参演人员至少录入一人"
        drill = {
            "id": _next_id(DRILL_TABLE),
            "plan_id": int(version["plan_id"]),
            "version_id": version["id"],
            "drill_no": drill_no,
            "drill_date": _clean_text(values.get("drill_date")),
            "accident_type": accident_type,
            "participants": [_clean_text(item) for item in participants if _clean_text(item)],
            "conclusion": _clean_text(values.get("conclusion")),
            "created_at": _now(),
        }
        _rows(DRILL_TABLE).append(drill)
        return self._drill_view(drill), "演练记录已登记"

    def add_rectification(
        self, drill_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        drill = store.find(DRILL_TABLE, drill_id)
        if drill is None:
            return None, f"演练记录 {drill_id} 不存在"
        content = _clean_text(values.get("content"))
        if not content:
            return None, "整改内容不能为空"
        rect = {
            "id": _next_id(RECTIFICATION_TABLE),
            "drill_id": drill_id,
            "plan_id": int(drill["plan_id"]),
            "content": content,
            "assignee": _clean_text(values.get("assignee")),
            "due_date": _clean_text(values.get("due_date")),
            "status": "待整改",
            "closed_at": "",
            "created_at": _now(),
        }
        _rows(RECTIFICATION_TABLE).append(rect)
        return self._rect_view(rect), "整改项已落入演练待办"

    def run_rectification_action(
        self, rect_id: int, action: str
    ) -> tuple[dict[str, Any] | None, str]:
        rect = store.find(RECTIFICATION_TABLE, rect_id)
        if rect is None:
            return None, f"整改项 {rect_id} 不存在"
        target = ACTION_RECT_RULES.get(action)
        if target is None:
            return None, f"动作「{action}」不属于整改项可执行范围"
        status = rect.get("status")
        if action == "开始整改" and status != "待整改":
            return None, "只有待整改项可以开始整改"
        if action == "闭环验证" and status != "整改中":
            return None, "整改中项才可以闭环验证"
        rect["status"] = target
        if target == "已闭环":
            rect["closed_at"] = _now()
        return self._rect_view(rect), f"整改项已{action}"

    def list_rectifications(
        self, *, status: str | None = None, assignee: str | None = None
    ) -> list[dict[str, Any]]:
        rows = list(_rows(RECTIFICATION_TABLE))
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if assignee:
            rows = [row for row in rows if assignee in str(row.get("assignee", ""))]
        rows.sort(key=lambda row: (row.get("status") == "已闭环", str(row.get("due_date", ""))))
        return [self._rect_view(row) for row in rows]

    # ------------------------------------------------------------------ 覆盖率
    def coverage_board(self) -> dict[str, Any]:
        """覆盖率按当前版本实时计算：分母=当前版本事故类别，分子=今年已演练的去重类别。

        历史演练挂在已归档版本上，不进入当前版本分子，保证换版后覆盖率按新版本重算。
        """
        year = datetime.now().year
        items: list[dict[str, Any]] = []
        for plan in _rows(PLAN_TABLE):
            current = self._current_version(plan)
            if current is None:
                items.append({
                    "plan_id": plan["id"], "plan_code": plan["plan_code"], "plan_name": plan["plan_name"],
                    "station": plan["station"], "current_version_no": None, "year": year,
                    "total_types": 0, "covered_types": 0, "coverage_rate": None,
                    "accident_types": [], "covered_accident_types": [],
                })
                continue
            types = list(current.get("accident_types") or [])
            covered = self._covered_types(current, year)
            items.append({
                "plan_id": plan["id"],
                "plan_code": plan["plan_code"],
                "plan_name": plan["plan_name"],
                "station": plan["station"],
                "current_version_no": current["version_no"],
                "year": year,
                "total_types": len(types),
                "covered_types": len(covered),
                "coverage_rate": round(len(covered) / len(types), 4) if types else None,
                "accident_types": types,
                "covered_accident_types": covered,
            })
        rates = [item["coverage_rate"] for item in items if item["coverage_rate"] is not None]
        overall = round(sum(rates) / len(rates), 4) if rates else None
        return {"year": year, "overall_rate": overall, "items": items}

    # ------------------------------------------------------------------ 导入
    def import_plans(
        self,
        rows: list[dict[str, Any]],
        *,
        import_type: str = "增量导入",
        operator: str = "",
        remark: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """同一份预案重复导入只留一条：按 预案编号+版本号 去重，逐行结果落库。

        存量回填时所有版本按发布日期视作已批复归档，最近发布的一版成为当前版本。
        """
        if not rows:
            return None, "导入内容为空"
        if import_type not in ("增量导入", "存量回填"):
            return None, "导入类型只能是增量导入或存量回填"

        batch_no = f"IMP-{datetime.now().strftime('%Y%m%d')}-{_next_id(IMPORT_TABLE):03d}"
        details: list[dict[str, Any]] = []
        created = duplicated = 0
        backfill_groups: dict[str, list[dict[str, Any]]] = {}
        # 同批次内也去重：重复行只在第一条入库。
        batch_seen: set[tuple[str, str]] = set()

        for index, raw in enumerate(rows, start=1):
            plan_code, version_no = _clean_text(raw.get("plan_code")), _clean_text(raw.get("version_no"))
            if not plan_code or not version_no:
                details.append({"row_no": index, "plan_code": plan_code, "version_no": version_no,
                                "result": "失败", "message": "缺少预案编号或版本号"})
                continue
            key = (plan_code, version_no)
            if key in batch_seen or self._find_version_by_code(plan_code, version_no) is not None:
                duplicated += 1
                details.append({"row_no": index, "plan_code": plan_code, "version_no": version_no,
                                "result": "重复", "message": "预案编号+版本号已存在，跳过"})
                continue
            plan = self._find_plan_by_code(plan_code)
            if plan is None:
                plan = {
                    "id": _next_id(PLAN_TABLE),
                    "plan_code": plan_code,
                    "plan_name": _clean_text(raw.get("plan_name")) or plan_code,
                    "station": _clean_text(raw.get("station")),
                    "current_version_id": None,
                    "created_at": _now(),
                }
                _rows(PLAN_TABLE).append(plan)
            types = _as_type_list(raw.get("accident_types"))
            publish_date = _clean_text(raw.get("publish_date"))
            version = {
                "id": _next_id(VERSION_TABLE),
                "plan_id": plan["id"],
                "version_no": version_no,
                "status": DRAFT,
                "accident_types": types,
                "publish_date": publish_date,
                "approved_by": _clean_text(raw.get("approved_by")),
                "content_summary": _clean_text(raw.get("content_summary")),
                "source": import_type,
                "immutable": False,
                "created_at": _now(),
            }
            _rows(VERSION_TABLE).append(version)
            batch_seen.add(key)
            created += 1
            if import_type == "存量回填":
                backfill_groups.setdefault(plan_code, []).append(version)
            details.append({"row_no": index, "plan_code": plan_code, "version_no": version_no,
                            "result": "新增", "message": f"{'回填' if import_type == '存量回填' else '新增'}版本 {version_no}"})

        if import_type == "存量回填":
            touched = set(backfill_groups)
            for version in (v for group in backfill_groups.values() for v in group):
                version["status"] = APPROVED
                version["immutable"] = True
                if not version.get("approved_by"):
                    version["approved_by"] = "存量回填"
            # 存量预案按发布日期回填：同一预案全部已批复版本里，发布日期最近的一版
            # 成为当前版本，此前的当前版本自动归档。
            for plan_code in touched:
                plan = self._find_plan_by_code(plan_code)
                if plan is None:
                    continue
                candidates = [
                    row for row in _rows(VERSION_TABLE)
                    if int(row.get("plan_id", 0)) == int(plan["id"])
                    and row.get("status") in IMMUTABLE_STATUSES and row.get("publish_date")
                ]
                latest = max(candidates, key=lambda row: (row["publish_date"], int(row["id"])), default=None)
                if latest is None:
                    continue
                for row in candidates:
                    row["status"] = APPROVED if int(row["id"]) == int(latest["id"]) else ARCHIVED
                plan["current_version_id"] = latest["id"]

        batch = {
            "id": _next_id(IMPORT_TABLE),
            "batch_no": batch_no,
            "import_type": import_type,
            "operator": _clean_text(operator) or "当前值班",
            "total_rows": len(rows),
            "created_count": created,
            "duplicated_count": duplicated,
            "remark": _clean_text(remark),
            "created_at": _now(),
            "details": details,
        }
        _rows(IMPORT_TABLE).append(batch)
        return batch, ""

    def list_imports(self) -> list[dict[str, Any]]:
        rows = sorted(_rows(IMPORT_TABLE), key=lambda row: int(row.get("id", 0)), reverse=True)
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ 内部
    def _plan_drills(self, plan_id: int) -> list[dict[str, Any]]:
        return [row for row in _rows(DRILL_TABLE) if int(row.get("plan_id", 0)) == plan_id]

    def _is_this_year(self, drill: dict[str, Any]) -> bool:
        return str(drill.get("drill_date", "")).startswith(str(datetime.now().year))

    def _covered_types(self, version: dict[str, Any], year: int) -> list[str]:
        types = version.get("accident_types") or []
        covered: list[str] = []
        for drill in _rows(DRILL_TABLE):
            if int(drill.get("version_id", 0)) != int(version["id"]):
                continue
            if not str(drill.get("drill_date", "")).startswith(str(year)):
                continue
            accident_type = drill.get("accident_type")
            if accident_type in types and accident_type not in covered:
                covered.append(accident_type)
        return covered

    def _current_version(self, plan: dict[str, Any]) -> dict[str, Any] | None:
        current_id = plan.get("current_version_id")
        if not current_id:
            return None
        return store.find(VERSION_TABLE, int(current_id))

    def _find_plan_by_code(self, plan_code: str) -> dict[str, Any] | None:
        for row in _rows(PLAN_TABLE):
            if row.get("plan_code") == plan_code:
                return row
        return None

    def _find_version(self, plan_id: int, version_no: str) -> dict[str, Any] | None:
        for row in _rows(VERSION_TABLE):
            if int(row.get("plan_id", 0)) == plan_id and row.get("version_no") == version_no:
                return row
        return None

    def _find_version_by_code(self, plan_code: str, version_no: str) -> dict[str, Any] | None:
        plan = self._find_plan_by_code(plan_code)
        if plan is None:
            return None
        return self._find_version(int(plan["id"]), version_no)

    def _plan_summary(self, plan: dict[str, Any]) -> dict[str, Any]:
        current = self._current_version(plan)
        year = datetime.now().year
        if current is not None:
            covered = self._covered_types(current, year)
            total = len(current.get("accident_types") or [])
            rate = round(len(covered) / total, 4) if total else None
        else:
            covered, total, rate = [], 0, None
        open_rect = sum(
            1 for row in _rows(RECTIFICATION_TABLE)
            if int(row.get("plan_id", 0)) == int(plan["id"]) and row.get("status") != "已闭环"
        )
        return {
            "id": plan["id"],
            "plan_code": plan["plan_code"],
            "plan_name": plan["plan_name"],
            "station": plan["station"],
            "current_version_id": plan.get("current_version_id"),
            "current_version_no": current["version_no"] if current else None,
            "current_version_status": current["status"] if current else None,
            "version_count": sum(
                1 for row in _rows(VERSION_TABLE) if int(row.get("plan_id", 0)) == int(plan["id"])
            ),
            "year": year,
            "total_types": total,
            "covered_types": len(covered),
            "coverage_rate": rate,
            "covered_accident_types": covered,
            "rectifications_open": open_rect,
            "created_at": plan.get("created_at"),
        }

    def _version_view(self, version: dict[str, Any]) -> dict[str, Any]:
        plan = store.find(PLAN_TABLE, int(version.get("plan_id", 0)))
        year = datetime.now().year
        is_current = bool(plan and plan.get("current_version_id") == version["id"])
        drills = [
            row for row in _rows(DRILL_TABLE)
            if int(row.get("version_id", 0)) == int(version["id"])
        ]
        year_drills = [row for row in drills if self._is_this_year(row)]
        types = list(version.get("accident_types") or [])
        covered = self._covered_types(version, year)
        return {
            "id": version["id"],
            "plan_id": version["plan_id"],
            "version_no": version["version_no"],
            "status": version["status"],
            "accident_types": types,
            "publish_date": version.get("publish_date", ""),
            "approved_by": version.get("approved_by", ""),
            "content_summary": version.get("content_summary", ""),
            "source": version.get("source", ""),
            "immutable": bool(version.get("immutable")),
            "is_current": is_current,
            "drill_count": len(drills),
            "drill_count_this_year": len(year_drills),
            "coverage_rate": round(len(covered) / len(types), 4) if types else None,
            "created_at": version.get("created_at"),
        }

    def _drill_view(self, drill: dict[str, Any]) -> dict[str, Any]:
        version = store.find(VERSION_TABLE, int(drill.get("version_id", 0)))
        plan = store.find(PLAN_TABLE, int(drill.get("plan_id", 0)))
        return {
            "id": drill["id"],
            "plan_id": drill["plan_id"],
            "plan_name": plan["plan_name"] if plan else "",
            "version_id": drill["version_id"],
            "version_no": version["version_no"] if version else "",
            "version_status": version["status"] if version else "",
            "drill_no": drill["drill_no"],
            "drill_date": drill["drill_date"],
            "accident_type": drill["accident_type"],
            "participants": list(drill.get("participants") or []),
            "conclusion": drill.get("conclusion", ""),
            "rectification_open": sum(
                1 for row in _rows(RECTIFICATION_TABLE)
                if int(row.get("drill_id", 0)) == int(drill["id"]) and row.get("status") != "已闭环"
            ),
            "created_at": drill.get("created_at"),
        }

    def _rect_view(self, rect: dict[str, Any]) -> dict[str, Any]:
        drill = store.find(DRILL_TABLE, int(rect.get("drill_id", 0)))
        plan = store.find(PLAN_TABLE, int(rect.get("plan_id", 0)))
        return {
            "id": rect["id"],
            "drill_id": rect["drill_id"],
            "drill_no": drill["drill_no"] if drill else "",
            "drill_date": drill["drill_date"] if drill else "",
            "accident_type": drill["accident_type"] if drill else "",
            "plan_id": rect["plan_id"],
            "plan_name": plan["plan_name"] if plan else "",
            "content": rect["content"],
            "assignee": rect.get("assignee", ""),
            "due_date": rect.get("due_date", ""),
            "status": rect["status"],
            "closed_at": rect.get("closed_at", ""),
            "created_at": rect.get("created_at"),
        }


service = EmergencyPlanService()
