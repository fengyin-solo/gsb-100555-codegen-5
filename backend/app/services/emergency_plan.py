"""应急预案演练台账业务规则。

口径约定：
- 一份预案多版本：已批复版本冻结、不许就地修改，只能基于现行版本新建草稿；
  批复通过后新版本成为唯一现行版本，旧版本保留为历史版本。
- 演练记录挂在具体版本下：覆盖率按该版本声明的事故类别计算；预案换版后，
  历史演练仍归属原版本，当前覆盖率按新版本重新统计。
- 演练发现的整改项落到演练待办，可认领、可闭环。
- 导入按预案编号（缺编号时按电站+预案名称）去重，同一份预案只留一条；
  每次导入无论新增还是重复都落一条导入记录。存量预案按发布日期回填，
  发布日期最新的已批复版本自动成为现行版本。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

PLAN_TABLE = "emergency_plan"
VERSION_TABLE = "emergency_plan_version"
DRILL_TABLE = "drill_record"
TODO_TABLE = "drill_todo"
IMPORT_LOG_TABLE = "plan_import_log"

# 事故类别参照目录：前端下拉用它，录入时允许补充版本声明之外的类别。
ACCIDENT_CATALOG = [
    "火灾", "触电", "防汛", "物体打击", "机械伤害", "中暑",
    "电池热失控", "全站停电", "电网解列", "台风", "泥石流", "高处坠落",
]
CONCLUSION_GRADES = ["优秀", "良好", "合格", "不合格"]
VERSION_DRAFT = "草稿"
VERSION_PENDING = "待批复"
VERSION_APPROVED = "已批复"
TODO_OPEN = "待整改"
TODO_DOING = "整改中"
TODO_CLOSED = "已闭环"

PLAN_REQUIRED = ["预案编号", "预案名称", "电站"]
VERSION_REQUIRED = ["版本号"]
DRILL_REQUIRED = ["演练名称", "演练日期", "事故类别", "plan_id", "version_id"]


def _today() -> str:
    return date.today().isoformat()


def _is_valid_date(value: Any) -> bool:
    """台账里的日期统一 YYYY-MM-DD，导入与录入都按这个口径校验。"""
    try:
        date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    return True


class EmergencyPlanService:
    # ---------- 通用辅助 ----------
    def _next_id(self, table: str) -> int:
        return max((int(row.get("id", 0)) for row in store.rows(table)), default=0) + 1

    def _find_plan(self, plan_id: int) -> dict[str, Any] | None:
        return store.find(PLAN_TABLE, plan_id)

    def _find_version(self, version_id: int) -> dict[str, Any] | None:
        return store.find(VERSION_TABLE, version_id)

    def _versions_of(self, plan_id: int) -> list[dict[str, Any]]:
        return [row for row in store.rows(VERSION_TABLE) if row["plan_id"] == plan_id]

    def _drills_of_plan(self, plan_id: int) -> list[dict[str, Any]]:
        return [row for row in store.rows(DRILL_TABLE) if row["plan_id"] == plan_id]

    def _todos_of_drill(self, drill_id: int) -> list[dict[str, Any]]:
        rows = [row for row in store.rows(TODO_TABLE) if row["drill_id"] == drill_id]
        return sorted(rows, key=lambda row: row["id"])

    def _find_open_draft(self, plan_id: int) -> dict[str, Any] | None:
        """草稿或待批复版本都算在途版本，一份预案同时只允许一条在途。"""
        for row in self._versions_of(plan_id):
            if row["status"] in (VERSION_DRAFT, VERSION_PENDING):
                return row
        return None

    def _coverage(
        self, version: dict[str, Any] | None, *, drills: list[dict[str, Any]] | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        """按版本声明的事故类别计算覆盖率，演练始终取挂在该版本下的。"""
        if version is None:
            return {"total_types": 0, "covered_count": 0, "rate": 0.0,
                    "covered_types": [], "uncovered_types": [], "extra_types": []}
        types: list[str] = list(version.get("accident_types") or [])
        linked = drills if drills is not None else [
            row for row in store.rows(DRILL_TABLE) if row["version_id"] == version["id"]
        ]
        linked = [row for row in linked if row["version_id"] == version["id"]]
        if year is not None:
            linked = [row for row in linked if str(row.get("演练日期", ""))[:4] == str(year)]
        drilled = {str(row.get("事故类别", "")) for row in linked if row.get("事故类别")}
        covered = [item for item in types if item in drilled]
        uncovered = [item for item in types if item not in drilled]
        extra = sorted(item for item in drilled if item not in types)
        rate = round(len(covered) / len(types) * 100, 1) if types else 0.0
        return {
            "total_types": len(types),
            "covered_count": len(covered),
            "rate": rate,
            "covered_types": covered,
            "uncovered_types": uncovered,
            "extra_types": extra,
        }

    def _serialize_drill(self, row: dict[str, Any], *, with_todos: bool = True) -> dict[str, Any]:
        plan = self._find_plan(int(row["plan_id"]))
        version = self._find_version(int(row["version_id"]))
        todos = self._todos_of_drill(int(row["id"])) if with_todos else []
        result = dict(row)
        result["预案名称"] = plan["预案名称"] if plan else "未知预案"
        result["电站"] = plan["电站"] if plan else ""
        result["版本号"] = version["版本号"] if version else "未知版本"
        result["待整改数"] = sum(1 for item in todos if item["status"] != TODO_CLOSED)
        result["todos"] = todos
        return result

    def _plan_row(self, plan: dict[str, Any], year: int) -> dict[str, Any]:
        current = self._find_version(int(plan.get("current_version_id") or 0))
        drills = self._drills_of_plan(int(plan["id"]))
        coverage = self._coverage(current, drills=drills, year=year)
        year_drills = [row for row in drills if str(row.get("演练日期", ""))[:4] == str(year)]
        open_todos = 0
        for row in drills:
            open_todos += sum(
                1 for item in self._todos_of_drill(int(row["id"]))
                if item["status"] != TODO_CLOSED
            )
        return {
            "id": plan["id"],
            "预案编号": plan["预案编号"],
            "预案名称": plan["预案名称"],
            "电站": plan["电站"],
            "当前版本": current["版本号"] if current else "无现行版本",
            "发布日期": current["发布日期"] if current else "",
            "批复人": current["批复人"] if current else "",
            "版本数": len(self._versions_of(int(plan["id"]))),
            "事故类别数": coverage["total_types"],
            "本年度覆盖率": f"{coverage['rate']}%（{coverage['covered_count']}/{coverage['total_types']}）",
            "覆盖率数值": coverage["rate"],
            "本年度演练数": len(year_drills),
            "待整改项": open_todos,
            "status": "现行有效" if current else "草稿中",
            "pending": open_todos > 0,
            "abnormal": coverage["covered_count"] < coverage["total_types"],
        }

    # ---------- 元数据与看板 ----------
    def meta(self) -> dict[str, Any]:
        return {
            "accident_catalog": ACCIDENT_CATALOG,
            "conclusion_grades": CONCLUSION_GRADES,
            "version_statuses": [VERSION_DRAFT, VERSION_PENDING, VERSION_APPROVED],
            "todo_statuses": [TODO_OPEN, TODO_DOING, TODO_CLOSED],
        }

    def stats(self, year: int | None = None) -> dict[str, Any]:
        year = year or date.today().year
        plans = store.rows(PLAN_TABLE)
        rates = []
        year_drill_ids: set[int] = set()
        for plan in plans:
            current = self._find_version(int(plan.get("current_version_id") or 0))
            drills = self._drills_of_plan(int(plan["id"]))
            coverage = self._coverage(current, drills=drills, year=year)
            if coverage["total_types"]:
                rates.append(coverage["rate"])
            for row in drills:
                if str(row.get("演练日期", ""))[:4] == str(year):
                    year_drill_ids.add(int(row["id"]))
        open_todos = sum(
            1 for row in store.rows(TODO_TABLE) if row["status"] != TODO_CLOSED
        )
        overdue = sum(
            1 for row in store.rows(TODO_TABLE)
            if row["status"] != TODO_CLOSED and row.get("整改期限") and str(row["整改期限"]) < _today()
        )
        return {
            "year": year,
            "cards": [
                {"label": "预案总数", "value": len(plans)},
                {"label": "现行版本平均覆盖率", "value": f"{round(sum(rates) / len(rates), 1) if rates else 0.0}%"},
                {"label": f"{year}年演练场次", "value": len(year_drill_ids)},
                {"label": "待整改项", "value": open_todos},
                {"label": "逾期未闭环", "value": overdue},
            ],
        }

    # ---------- 预案 ----------
    def list_plans(
        self, *, keyword: str | None = None, station: str | None = None,
        year: int | None = None, page: int = 1, size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        year = year or date.today().year
        rows = store.rows(PLAN_TABLE)
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("预案编号", "")) or keyword in str(row.get("预案名称", ""))
            ]
        if station:
            rows = [row for row in rows if station in str(row.get("电站", ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [self._plan_row(row, year) for row in rows[start:start + size]]
        return page_rows, total

    def get_plan(self, plan_id: int, year: int | None = None) -> dict[str, Any] | None:
        plan = self._find_plan(plan_id)
        if plan is None:
            return None
        year = year or date.today().year
        current = self._find_version(int(plan.get("current_version_id") or 0))
        drills = self._drills_of_plan(plan_id)
        versions = []
        for version in sorted(self._versions_of(plan_id), key=lambda row: row["id"], reverse=True):
            versions.append({
                "id": version["id"],
                "版本号": version["版本号"],
                "status": version["status"],
                "is_current": bool(version.get("is_current")),
                "发布日期": version.get("发布日期"),
                "批复日期": version.get("批复日期"),
                "批复人": version.get("批复人"),
                "事故类别": version.get("accident_types") or [],
                "accident_types": version.get("accident_types") or [],
                "预案内容": version.get("预案内容") or "",
                "建版日期": version.get("建版日期"),
                "演练场次": sum(1 for row in drills if row["version_id"] == version["id"]),
                "coverage_year": self._coverage(version, drills=drills, year=year),
                "coverage_all": self._coverage(version, drills=drills),
            })
        drill_rows = [
            self._serialize_drill(row)
            for row in sorted(drills, key=lambda item: str(item.get("演练日期", "")), reverse=True)
        ]
        result = dict(plan)
        result["current_version"] = self._version_detail(current) if current else None
        result["coverage_year"] = self._coverage(current, drills=drills, year=year)
        result["versions"] = versions
        result["drills"] = drill_rows
        return result

    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in PLAN_REQUIRED if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        plan_no = str(values["预案编号"]).strip()
        station = str(values["电站"]).strip()
        name = str(values["预案名称"]).strip()
        duplicate = self._find_plan_by_natural_key(plan_no, station, name)
        if duplicate is not None:
            return None, [f"预案 {plan_no} 已存在（{duplicate['电站']}），请勿重复登记"]
        rows = store.rows(PLAN_TABLE)
        plan = {
            "id": self._next_id(PLAN_TABLE),
            "预案编号": plan_no,
            "预案名称": name,
            "电站": station,
            "current_version_id": None,
            "建档日期": _today(),
        }
        rows.append(plan)
        return plan, []

    def _find_plan_by_natural_key(
        self, plan_no: str, station: str, name: str,
    ) -> dict[str, Any] | None:
        for row in store.rows(PLAN_TABLE):
            if str(row.get("预案编号", "")).strip() == plan_no:
                return row
        for row in store.rows(PLAN_TABLE):
            if str(row.get("电站", "")).strip() == station and str(row.get("预案名称", "")).strip() == name:
                return row
        return None

    # ---------- 版本 ----------
    def _version_detail(self, version: dict[str, Any] | None) -> dict[str, Any] | None:
        if version is None:
            return None
        plan = self._find_plan(int(version["plan_id"]))
        drills = [
            self._serialize_drill(row, with_todos=False)
            for row in store.rows(DRILL_TABLE) if row["version_id"] == version["id"]
        ]
        result = dict(version)
        result["预案编号"] = plan["预案编号"] if plan else ""
        result["预案名称"] = plan["预案名称"] if plan else ""
        result["电站"] = plan["电站"] if plan else ""
        result["drills"] = sorted(drills, key=lambda item: str(item.get("演练日期", "")), reverse=True)
        result["coverage_year"] = self._coverage(version, year=date.today().year)
        result["coverage_all"] = self._coverage(version)
        return result

    def get_version(self, version_id: int) -> dict[str, Any] | None:
        return self._version_detail(self._find_version(version_id))

    def create_version(
        self, plan_id: int, values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        plan = self._find_plan(plan_id)
        if plan is None:
            return None, f"预案 {plan_id} 不存在"
        version_no = str(values.get("版本号") or "").strip()
        if not version_no:
            return None, "版本号必填"
        if any(row["版本号"] == version_no for row in self._versions_of(plan_id)):
            return None, f"版本 {version_no} 已存在，改一版需使用新版本号"
        if self._find_open_draft(plan_id) is not None:
            return None, "已有在途的草稿或待批复版本，请先批复或作废后再建新版"
        current = self._find_version(int(plan.get("current_version_id") or 0))
        version = {
            "id": self._next_id(VERSION_TABLE),
            "plan_id": plan_id,
            "版本号": version_no,
            "status": VERSION_DRAFT,
            "is_current": False,
            "accident_types": list(values.get("accident_types") or (current.get("accident_types") if current else [])),
            "预案内容": str(values.get("预案内容") or (current.get("预案内容") if current else "")),
            "发布日期": None,
            "批复日期": None,
            "批复人": None,
            "建版日期": _today(),
        }
        store.rows(VERSION_TABLE).append(version)
        return version, "新版本草稿已建立，可继续编辑后提交批复"

    def update_version(
        self, version_id: int, values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        version = self._find_version(version_id)
        if version is None:
            return None, f"版本 {version_id} 不存在"
        if version["status"] != VERSION_DRAFT:
            return None, "已批复版本不允许就地修改，如需调整请基于现行版本新建草稿"
        version_no = str(values.get("版本号") or "").strip()
        if version_no:
            exists = any(
                row["版本号"] == version_no and row["id"] != version_id
                for row in self._versions_of(int(version["plan_id"]))
            )
            if exists:
                return None, f"版本号 {version_no} 已被占用"
            version["版本号"] = version_no
        if values.get("事故类别") is not None:
            types = values["事故类别"]
            version["accident_types"] = [str(item).strip() for item in types if str(item).strip()]
        if values.get("预案内容") is not None:
            version["预案内容"] = str(values.get("预案内容") or "")
        return version, "草稿已保存，已批复版本不受影响"

    def run_version_action(
        self, version_id: int, action: str, values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        version = self._find_version(version_id)
        if version is None:
            return None, f"版本 {version_id} 不存在"
        status = version["status"]
        if action == "提交批复":
            if status != VERSION_DRAFT:
                return None, "仅草稿版本可提交批复"
            if not version.get("accident_types"):
                return None, "请至少声明一类覆盖事故，便于演练覆盖率计算"
            version["status"] = VERSION_PENDING
            return version, "版本已提交，等待批复"
        if action == "撤回批复":
            if status != VERSION_PENDING:
                return None, "仅待批复版本可撤回"
            version["status"] = VERSION_DRAFT
            return version, "版本已撤回到草稿"
        if action == "批复":
            if status != VERSION_PENDING:
                return None, "仅待批复版本可执行批复"
            approver = str(values.get("批复人") or "").strip()
            if not approver:
                return None, "批复时必须填写批复人"
            publish_date = str(values.get("发布日期") or _today()).strip()
            if not _is_valid_date(publish_date):
                return None, "发布日期需为 YYYY-MM-DD 格式"
            plan = self._find_plan(int(version["plan_id"]))
            previous = self._find_version(int(plan.get("current_version_id") or 0)) if plan else None
            # 唯一现行版本：旧版本保留已批复内容，只是摘掉现行标记。
            for row in self._versions_of(int(version["plan_id"])):
                row["is_current"] = False
            version["status"] = VERSION_APPROVED
            version["is_current"] = True
            version["批复人"] = approver
            version["发布日期"] = publish_date
            version["批复日期"] = _today()
            if plan is not None:
                plan["current_version_id"] = version["id"]
            message = "版本已批复并成为现行版本"
            if previous is not None:
                message += f"，原版本 {previous['版本号']} 已转为历史版本"
            return version, message
        return None, f"动作「{action}」不属于版本流转范围"

    def discard_version(self, version_id: int) -> tuple[bool, str]:
        """作废在途版本；已批复版本是台账凭证，不允许删除。"""
        version = self._find_version(version_id)
        if version is None:
            return False, f"版本 {version_id} 不存在"
        if version["status"] == VERSION_APPROVED:
            return False, "已批复版本不允许删除，只能由新版本替代"
        rows = store.rows(VERSION_TABLE)
        rows[:] = [row for row in rows if row["id"] != version_id]
        return True, "在途版本已作废"

    # ---------- 演练记录 ----------
    def list_drills(
        self, *, plan_id: int | None = None, version_id: int | None = None,
        year: int | None = None, keyword: str | None = None,
        page: int = 1, size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(DRILL_TABLE)
        if plan_id is not None:
            rows = [row for row in rows if row["plan_id"] == plan_id]
        if version_id is not None:
            rows = [row for row in rows if row["version_id"] == version_id]
        if year is not None:
            rows = [row for row in rows if str(row.get("演练日期", ""))[:4] == str(year)]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("演练编号", "")) or keyword in str(row.get("演练名称", ""))
            ]
        rows = sorted(rows, key=lambda item: str(item.get("演练日期", "")), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._serialize_drill(row) for row in rows[start:start + size]], total

    def get_drill(self, drill_id: int) -> dict[str, Any] | None:
        row = store.find(DRILL_TABLE, drill_id)
        return self._serialize_drill(row) if row else None

    def create_drill(
        self, values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in DRILL_REQUIRED if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        plan = self._find_plan(int(values["plan_id"]))
        if plan is None:
            return None, f"预案 {values['plan_id']} 不存在"
        version = self._find_version(int(values["version_id"]))
        if version is None or version["plan_id"] != plan["id"]:
            return None, "所选版本不属于该预案"
        if version["status"] != VERSION_APPROVED:
            return None, "演练只能挂在已批复版本下，请先完成批复"
        drill_date = str(values["演练日期"]).strip()
        if not _is_valid_date(drill_date):
            return None, "演练日期需为 YYYY-MM-DD 格式"
        grade = str(values.get("演练结论评级") or "").strip()
        if grade and grade not in CONCLUSION_GRADES:
            return None, f"演练结论评级需为：{'、'.join(CONCLUSION_GRADES)}"
        participants = values.get("参演人员") or []
        clean_participants = [
            {"姓名": str(item.get("姓名", "")).strip(), "岗位": str(item.get("岗位", "")).strip()}
            for item in participants if str(item.get("姓名", "")).strip()
        ]
        drill_no = self._next_drill_no(drill_date[:4])
        drill = {
            "id": self._next_id(DRILL_TABLE),
            "演练编号": drill_no,
            "plan_id": plan["id"],
            "version_id": version["id"],
            "演练名称": str(values["演练名称"]).strip(),
            "演练日期": drill_date,
            "事故类别": str(values["事故类别"]).strip(),
            "演练地点": str(values.get("演练地点") or "").strip(),
            "总指挥": str(values.get("总指挥") or "").strip(),
            "参演人员": clean_participants,
            "演练结论评级": grade or "合格",
            "演练结论": str(values.get("演练结论") or "").strip(),
            "登记日期": _today(),
            "pending": False,
            "abnormal": grade == "不合格",
        }
        store.rows(DRILL_TABLE).append(drill)
        # 整改项逐条落到演练待办；有未闭环项时演练与预案进入待处理口径。
        for item in values.get("整改项") or []:
            content = str(item.get("整改内容", "")).strip()
            if not content:
                continue
            self._create_todo_row(
                drill["id"], content,
                str(item.get("责任人") or "").strip(),
                str(item.get("整改期限") or "").strip(),
            )
        return self.get_drill(drill["id"]), "演练记录已登记，整改项已进入演练待办"

    def _next_drill_no(self, year: str) -> str:
        seq = 1
        for row in store.rows(DRILL_TABLE):
            no = str(row.get("演练编号", ""))
            if no.startswith(f"YL-{year}-"):
                try:
                    seq = max(seq, int(no.rsplit("-", 1)[1]) + 1)
                except ValueError:
                    continue
        return f"YL-{year}-{seq:03d}"

    # ---------- 演练待办 ----------
    def _create_todo_row(
        self, drill_id: int, content: str, owner: str, due_date: str,
    ) -> dict[str, Any]:
        if due_date and not _is_valid_date(due_date):
            raise ValueError("整改期限需为 YYYY-MM-DD 格式")
        todo = {
            "id": self._next_id(TODO_TABLE),
            "drill_id": drill_id,
            "整改内容": content,
            "责任人": owner,
            "整改期限": due_date,
            "status": TODO_OPEN,
            "闭环日期": None,
            "pending": True,
            "abnormal": bool(due_date and due_date < _today()),
        }
        store.rows(TODO_TABLE).append(todo)
        self._refresh_drill_flags(drill_id)
        return todo

    def add_todo(self, drill_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        drill = store.find(DRILL_TABLE, drill_id)
        if drill is None:
            return None, f"演练记录 {drill_id} 不存在"
        content = str(values.get("整改内容") or "").strip()
        if not content:
            return None, "整改内容必填"
        try:
            todo = self._create_todo_row(
                drill_id, content,
                str(values.get("责任人") or "").strip(),
                str(values.get("整改期限") or "").strip(),
            )
        except ValueError as exc:
            return None, str(exc)
        return todo, "整改项已追加到演练待办"

    def list_todos(
        self, *, status: str | None = None, drill_id: int | None = None,
        page: int = 1, size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(TODO_TABLE)
        if status:
            rows = [row for row in rows if row["status"] == status]
        if drill_id is not None:
            rows = [row for row in rows if row["drill_id"] == drill_id]
        enriched = []
        for row in rows:
            drill = store.find(DRILL_TABLE, int(row["drill_id"]))
            item = dict(row)
            if drill:
                plan = self._find_plan(int(drill["plan_id"]))
                item["演练编号"] = drill["演练编号"]
                item["演练名称"] = drill["演练名称"]
                item["电站"] = plan["电站"] if plan else ""
            enriched.append(item)
        enriched.sort(key=lambda row: (row["status"] == TODO_CLOSED, str(row.get("整改期限") or "9999")))
        total = len(enriched)
        start = max(page - 1, 0) * size
        return enriched[start:start + size], total

    def run_todo_action(
        self, todo_id: int, action: str,
    ) -> tuple[dict[str, Any] | None, str]:
        todo = store.find(TODO_TABLE, todo_id)
        if todo is None:
            return None, f"待办 {todo_id} 不存在"
        if action == "认领整改":
            if todo["status"] != TODO_OPEN:
                return None, "仅待整改项可认领"
            todo["status"] = TODO_DOING
        elif action == "完成闭环":
            if todo["status"] not in (TODO_OPEN, TODO_DOING):
                return None, "待办已闭环，无需重复操作"
            todo["status"] = TODO_CLOSED
            todo["闭环日期"] = _today()
        else:
            return None, f"动作「{action}」不属于演练待办流转范围"
        todo["pending"] = todo["status"] != TODO_CLOSED
        todo["abnormal"] = todo["pending"] and bool(
            todo.get("整改期限") and str(todo["整改期限"]) < _today()
        )
        self._refresh_drill_flags(int(todo["drill_id"]))
        return todo, f"整改项已{action}"

    def _refresh_drill_flags(self, drill_id: int) -> None:
        drill = store.find(DRILL_TABLE, drill_id)
        if drill is None:
            return
        todos = self._todos_of_drill(drill_id)
        drill["pending"] = any(item["status"] != TODO_CLOSED for item in todos)
        plan = self._find_plan(int(drill["plan_id"]))
        if plan is not None:
            plan_open = any(
                item["status"] != TODO_CLOSED
                for row in self._drills_of_plan(int(plan["id"]))
                for item in self._todos_of_drill(int(row["id"]))
            )
            plan["pending"] = plan_open

    # ---------- 导入 ----------
    def import_plans(
        self, *, items: list[dict[str, Any]], source: str, operator: str,
    ) -> tuple[dict[str, Any], str]:
        """批量导入预案版本；重复预案只留一条，每次调用都落一条导入记录。"""
        rows = store.rows(IMPORT_LOG_TABLE)
        log_id = self._next_id(IMPORT_LOG_TABLE)
        batch_no = f"IMP-{_today()}-{log_id:03d}"
        details: list[dict[str, Any]] = []
        created = duplicated = failed = 0
        for index, raw in enumerate(items, start=1):
            plan_no = str(raw.get("预案编号") or "").strip()
            name = str(raw.get("预案名称") or "").strip()
            station = str(raw.get("电站") or "").strip()
            version_no = str(raw.get("版本号") or "").strip()
            publish_date = str(raw.get("发布日期") or "").strip()
            accident_types = [str(item).strip() for item in (raw.get("事故类别") or []) if str(item).strip()]
            missing = [
                label for label, value in (
                    ("预案编号", plan_no), ("预案名称", name), ("电站", station),
                    ("版本号", version_no), ("发布日期", publish_date),
                ) if not value
            ]
            if missing:
                failed += 1
                details.append({
                    "行号": index, "结果": "失败", "预案编号": plan_no, "版本号": version_no,
                    "说明": f"缺少必填字段：{'、'.join(missing)}",
                })
                continue
            if not _is_valid_date(publish_date):
                failed += 1
                details.append({
                    "行号": index, "结果": "失败", "预案编号": plan_no, "版本号": version_no,
                    "说明": "发布日期需为 YYYY-MM-DD 格式",
                })
                continue
            plan = self._find_plan_by_natural_key(plan_no, station, name)
            if plan is not None and any(
                row["版本号"] == version_no for row in self._versions_of(int(plan["id"]))
            ):
                # 同一份预案同一版本重复导入：只留一条，不再新增。
                duplicated += 1
                details.append({
                    "行号": index, "结果": "重复跳过", "预案编号": plan_no, "版本号": version_no,
                    "说明": f"预案 {plan_no} 版本 {version_no} 已存在，未重复建档",
                })
                continue
            if plan is None:
                plan = {
                    "id": self._next_id(PLAN_TABLE),
                    "预案编号": plan_no,
                    "预案名称": name,
                    "电站": station,
                    "current_version_id": None,
                    "建档日期": _today(),
                }
                store.rows(PLAN_TABLE).append(plan)
                action_label = "新建预案"
            else:
                action_label = "追加版本"
            version = {
                "id": self._next_id(VERSION_TABLE),
                "plan_id": plan["id"],
                "版本号": version_no,
                "status": VERSION_APPROVED,
                "is_current": False,
                "accident_types": accident_types,
                "预案内容": str(raw.get("预案内容") or "").strip(),
                "发布日期": publish_date,
                "批复日期": publish_date,
                "批复人": str(raw.get("批复人") or "").strip(),
                "建版日期": _today(),
            }
            store.rows(VERSION_TABLE).append(version)
            # 存量回填：发布日期最新的已批复版本为现行版本。
            current = self._find_version(int(plan.get("current_version_id") or 0))
            if current is None or publish_date >= str(current.get("发布日期") or ""):
                if current is not None:
                    current["is_current"] = False
                version["is_current"] = True
                plan["current_version_id"] = version["id"]
            created += 1
            details.append({
                "行号": index, "结果": action_label, "预案编号": plan_no, "版本号": version_no,
                "说明": f"{action_label}成功，发布日期 {publish_date}",
            })
        log = {
            "id": log_id,
            "导入批号": batch_no,
            "来源": source or "文档导入",
            "导入人": operator or "值班管理员",
            "导入时间": _today(),
            "总行数": len(items),
            "新增数": created,
            "重复跳过数": duplicated,
            "失败数": failed,
            "明细": details,
            "pending": False,
            "abnormal": failed > 0,
        }
        rows.append(log)
        message = f"导入完成：新增 {created} 条，重复跳过 {duplicated} 条，失败 {failed} 条"
        return log, message

    def list_import_logs(
        self, *, page: int = 1, size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = sorted(store.rows(IMPORT_LOG_TABLE), key=lambda row: int(row["id"]), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_import_log(self, log_id: int) -> dict[str, Any] | None:
        return store.find(IMPORT_LOG_TABLE, log_id)


service = EmergencyPlanService()
