import json
import os
import re
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Dict, List, Optional

from loguru import logger

from config import cfg
from company_table import get_sql_search_cursor, load_company_table
from file import add_growth_rate_in_table
from file import add_text_compare_in_table
from file import load_pdf_info
from file import load_pdf_pure_text
from file import load_tables_of_years
from file import load_test_questions
from file import load_total_tables
from file import table_to_text
from project_meta import PROJECT_DESCRIPTION
from project_meta import PROJECT_NAME
from project_meta import PROJECT_SUBTITLE
from prompt_util import get_prompt_single_question
from prompt_registry import get_prompt_version_snapshot
import prompt_util
import question_util
from recall_report_names import recall_pdf_tables
from recall_report_text import recall_annual_report_texts
import sql_correct_util
import type1
import type2


QUESTION_ROUTE_METADATA = {
    "A": {
        "route_name": "structured_precise_qa",
        "route_label": "结构化精准问答",
        "output_type": "直接答案 + 命中字段证据",
        "execution_path": [
            "Query Router",
            "Document Evidence Retrieval",
            "Synthesis",
        ],
        "valid_tables": ["basic_info"],
    },
    "B": {
        "route_name": "structured_precise_qa",
        "route_label": "结构化精准问答",
        "output_type": "直接答案 + 命中表格证据",
        "execution_path": [
            "Query Router",
            "Document Evidence Retrieval",
            "Synthesis",
        ],
        "valid_tables": ["employee_info", "dev_info"],
    },
    "C": {
        "route_name": "structured_precise_qa",
        "route_label": "结构化精准问答",
        "output_type": "直接答案 + 字段来源说明",
        "execution_path": [
            "Query Router",
            "Document Evidence Retrieval",
            "Synthesis",
        ],
        "valid_tables": ["cbs_info", "cscf_info", "cis_info"],
    },
    "D": {
        "route_name": "formula_analysis",
        "route_label": "计算型问答",
        "output_type": "计算过程 + 最终数值答案",
        "execution_path": [
            "Query Router",
            "Document Evidence Retrieval",
            "Synthesis",
        ],
        "valid_tables": ["basic_info", "employee_info", "dev_info", "cbs_info", "cscf_info", "cis_info"],
    },
    "E": {
        "route_name": "structured_query",
        "route_label": "SQL / 统计分析",
        "output_type": "SQL 结果 + 自然语言答案",
        "execution_path": [
            "Query Router",
            "Structured Query",
            "Synthesis",
        ],
        "valid_tables": ["company_table"],
    },
    "F": {
        "route_name": "text_synthesis",
        "route_label": "文本总结问答",
        "output_type": "总结型答案 + 证据片段",
        "execution_path": [
            "Query Router",
            "Document Evidence Retrieval",
            "Synthesis",
        ],
        "valid_tables": ["annual_report_text"],
    },
    "G": {
        "route_name": "structured_fallback",
        "route_label": "结构化问答兜底",
        "output_type": "直接答案 + 路由修正说明",
        "execution_path": [
            "Query Router",
            "Document Evidence Retrieval",
            "Synthesis",
        ],
        "valid_tables": ["basic_info", "employee_info", "dev_info", "cbs_info", "cscf_info", "cis_info"],
    },
}

TARGET_ARCHITECTURE_CODE_MAP = {
    "Query Router": [
        "generate_answer_with_classify.py::do_classification",
        "financial_agent_workflow.py::QueryRouter",
    ],
    "Document Evidence Retrieval": [
        "financial_agent_workflow.py::DocumentEvidenceRetriever",
        "recall_report_text.py::recall_annual_report_texts",
        "recall_report_names.py::recall_pdf_tables",
        "file.py::table_to_text",
    ],
    "Structured Query": [
        "financial_agent_workflow.py::StructuredQueryExecutor",
        "generate_answer_with_classify.py::do_sql_generation",
        "sql_correct_util.py",
        "company_table.py",
    ],
    "Synthesis": [
        "financial_agent_workflow.py::AnswerSynthesizer",
        "type1.py",
        "type2.py",
        "prompt_util.py",
    ],
}


STRUCTURED_ROUTE_TYPES = {"A", "B", "C", "G"}
DEFAULT_ANSWER_TEMPLATE = "经查询，无法回答{}"
SQL_ALLOWED_TABLES = {"company_table"}
SQL_BLOCKED_KEYWORDS = ("insert", "update", "delete", "drop", "alter", "create", "attach", "pragma")
AMOUNT_UNIT_HINTS = (
    "资产", "负债", "利润", "收入", "成本", "资金", "现金", "账款", "薪酬", "费用",
    "税", "款", "存货", "应收", "应付", "收益", "公积", "股本", "流量",
)
COUNT_UNIT_HINTS = ("人数", "员工", "人员", "职工", "博士", "硕士", "本科", "大专")
RATIO_UNIT_HINTS = ("比率", "比例", "增长率", "毛利率", "净利率", "收益率", "占比")


@dataclass
class QuestionContext:
    question_id: int
    original_question: str
    normalized_question: str
    question_type: str
    route_name: str
    route_label: str
    output_type: str
    execution_path: List[str]
    question_keywords: List[str] = field(default_factory=list)
    years: List[str] = field(default_factory=list)
    matched_pdf_names: List[str] = field(default_factory=list)
    company_abbrs: List = field(default_factory=list)
    company: Optional[str] = None
    abbr: Optional[str] = None
    code: Optional[str] = None
    real_company: Optional[str] = None
    sql: Optional[str] = None


@dataclass
class EvidenceItem:
    evidence_type: str
    source: str
    content: str
    year: Optional[str] = None
    table_name: Optional[str] = None


@dataclass
class WorkflowResult:
    success: bool
    status: str
    answer: str
    question_type: str
    route_name: str
    route_label: str
    output_type: str
    execution_path: List[str]
    question_keywords: List[str]
    failure_reason: Optional[str] = None
    error_message: Optional[str] = None
    evidence: List[EvidenceItem] = field(default_factory=list)
    route_trace: Dict = field(default_factory=dict)
    context: Optional[QuestionContext] = None


def _load_question_artifact(directory_name, question_id, field_name, default_value):
    artifact_path = os.path.join(cfg.DATA_PATH, directory_name, "{}.csv".format(question_id))
    if not os.path.exists(artifact_path):
        return default_value
    with open(artifact_path, "r", encoding="utf-8") as file_obj:
        result = json.load(file_obj)
    return result.get(field_name, default_value)


class QueryRouter:
    def __init__(self, pdf_info):
        self.pdf_info = pdf_info

    def build_context(self, question, runtime_artifacts=None):
        runtime_artifacts = runtime_artifacts or {}
        question_type = runtime_artifacts.get(
            "class",
            _load_question_artifact("classify", question["id"], "class", "F"),
        )
        question_keywords = runtime_artifacts.get(
            "keywords",
            _load_question_artifact("keywords", question["id"], "keywords", []),
        )
        sql = runtime_artifacts.get(
            "sql",
            _load_question_artifact("sql", question["id"], "sql", None),
        )

        normalized_question = re.sub(r"[\(\)（）]", "", question["question"])
        years = question_util.get_years_of_question(normalized_question)
        matched_pdf_names = question_util.get_match_pdf_names(normalized_question, self.pdf_info)
        company_abbrs = question_util.get_company_name_and_abbr_code_of_question(
            matched_pdf_names, self.pdf_info
        )

        route_meta = QUESTION_ROUTE_METADATA.get(question_type, QUESTION_ROUTE_METADATA["F"])

        company = None
        abbr = None
        code = None
        real_company = None
        if company_abbrs:
            company, abbr, code = company_abbrs[0]
            real_company = company if company in normalized_question else abbr

        return QuestionContext(
            question_id=question["id"],
            original_question=question["question"],
            normalized_question=normalized_question,
            question_type=question_type,
            route_name=route_meta["route_name"],
            route_label=route_meta["route_label"],
            output_type=route_meta["output_type"],
            execution_path=route_meta["execution_path"],
            question_keywords=question_keywords,
            years=years,
            matched_pdf_names=matched_pdf_names,
            company_abbrs=company_abbrs,
            company=company,
            abbr=abbr,
            code=code,
            real_company=real_company,
            sql=sql,
        )


class DocumentEvidenceRetriever:
    def __init__(self, pdf_info, pdf_tables):
        self.pdf_info = pdf_info
        self.pdf_tables = pdf_tables

    @staticmethod
    def _normalize_text_block(text):
        text = str(text or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _rank_text_block(text, query_tokens):
        normalized = DocumentEvidenceRetriever._normalize_text_block(text)
        if not normalized:
            return -1
        score = 0
        for token in query_tokens:
            if token and token in normalized:
                score += max(len(token), 2)
        if re.search(r"[一二三四五六七八九十\d]+、", normalized[:20]):
            score += 1
        return score

    @staticmethod
    def _classify_open_question(context):
        question = context.normalized_question
        if re.search(r"(什么是|是指什么|定义)", question):
            return "definition"
        if re.search(r"(简要介绍|概述|详情|情况|事项|主要|客户|社会责任|重整)", question):
            return "report_section"
        return "analysis"

    @staticmethod
    def _extract_section_hints(context):
        question = context.normalized_question
        hints = []
        patterns = [
            r"报告期内(.+?)(?:的详情|详情|情况|的情况)",
            r"简要介绍(.+?)(?:的详情|详情|情况|的情况)",
            r"概述(.+?)(?:的详情|详情|情况|的情况)",
            r"(.+?相关事项)",
            r"(主要销售客户(?:及主要供应商情况)?)",
            r"(主要供应商(?:情况)?)",
            r"(主要控股参股公司分析)",
            r"(关键审计事项)",
            r"(处罚及整改情况)",
            r"(面临退市情况)",
            r"(诚信状况)",
            r"(公司员工情况)",
            r"(主要会计数据和财务指标)",
            r"(社会责任情况)",
            r"(破产重整相关事项)",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, question):
                text = str(match).strip("，。？? ")
                text = re.sub(r"^(公司|报告期内)", "", text).strip()
                if len(text) >= 2 and text not in hints:
                    hints.append(text)
        for keyword in context.question_keywords:
            if keyword and len(keyword) >= 2 and keyword not in hints:
                hints.append(keyword)
        return hints[:6]

    @staticmethod
    def _is_heading_line(line):
        line = str(line or "").strip()
        if not line or len(line) > 60:
            return False
        patterns = [
            r"^第[一二三四五六七八九十百]+节",
            r"^[一二三四五六七八九十]+、",
            r"^（[一二三四五六七八九十]+）",
            r"^\([一二三四五六七八九十]+\)",
            r"^\d+[、.]",
        ]
        return any(re.match(pattern, line) for pattern in patterns)

    @staticmethod
    def _clean_open_lines(lines):
        cleaned = []
        for line in lines:
            line = str(line or "").strip()
            line = re.sub(r"\s+", " ", line)
            if not line:
                continue
            if len(line) <= 1:
                continue
            cleaned.append(line)
        return cleaned

    def _load_open_lines(self, key):
        page_items = load_pdf_pure_text(key)
        lines = []
        for item in page_items:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            lines.extend(text.splitlines())
        return self._clean_open_lines(lines)

    def _build_section_blocks(self, lines):
        if not lines:
            return []
        sections = []
        current_title = "文档摘要"
        current_lines = []
        for line in lines:
            if self._is_heading_line(line):
                if current_lines:
                    sections.append((current_title, current_lines))
                current_title = line
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            sections.append((current_title, current_lines))
        return sections

    def _retrieve_definition_blocks(self, context, lines):
        keywords = [token for token in context.question_keywords if token]
        matched = []
        for idx, line in enumerate(lines):
            if not any(token in line for token in keywords):
                continue
            if re.search(r"(是指|指的是|指|包括|属于)", line):
                window = lines[max(0, idx - 1): min(len(lines), idx + 3)]
                matched.append(" ".join(window))
        return matched[:3]

    def _retrieve_section_blocks(self, context, lines):
        sections = self._build_section_blocks(lines)
        if not sections:
            return []
        section_hints = self._extract_section_hints(context)
        query_tokens = list(section_hints)
        query_tokens.extend(re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", context.normalized_question))
        ranked = []
        for title, content_lines in sections:
            body = " ".join(content_lines[:40])
            text = "{}\n{}".format(title, body).strip()
            score = self._rank_text_block(title, query_tokens) * 4 + self._rank_text_block(body, query_tokens)
            for hint in section_hints:
                if hint in title:
                    score += max(len(hint), 4) * 4
                elif hint in body[:200]:
                    score += max(len(hint), 4) * 2
            ranked.append((score, text))
        ranked.sort(key=lambda item: (-item[0], len(item[1])))
        return [text[:900] for score, text in ranked if score >= 1][:3]

    def _compress_open_text_blocks(self, context, text_blocks):
        query_tokens = []
        if context.real_company:
            query_tokens.append(context.real_company)
        query_tokens.extend(context.years)
        query_tokens.extend([token for token in context.question_keywords if token])
        normalized_question = context.normalized_question
        for token in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", normalized_question):
            if token not in query_tokens:
                query_tokens.append(token)

        seen = set()
        ranked_blocks = []
        for text in text_blocks:
            normalized = self._normalize_text_block(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ranked_blocks.append((self._rank_text_block(normalized, query_tokens), normalized))

        ranked_blocks.sort(key=lambda item: (-item[0], len(item[1])))
        filtered = [text[:600] for score, text in ranked_blocks if score >= 1]
        if not filtered:
            filtered = [text[:600] for _, text in ranked_blocks]
        return filtered[:3]

    def retrieve_structured_background(self, context):
        if not context.company:
            return {"background": "", "tot_text": "", "matched_rows": []}

        valid_tables = QUESTION_ROUTE_METADATA[context.question_type]["valid_tables"]
        background = ""
        total_matched_rows = []

        for year in context.years:
            pdf_table = load_tables_of_years(context.company, [year], self.pdf_tables, self.pdf_info)
            background += "已知{}(简称:{},证券代码:{}){}年的资料如下:\n    ".format(
                context.company, context.abbr, context.code, year
            )

            matched_table_rows = []
            for keyword in context.question_keywords:
                matched_table_rows.extend(
                    recall_pdf_tables(
                        keyword,
                        [year],
                        pdf_table,
                        min_match_number=3,
                        valid_tables=valid_tables,
                    )
                )

            if len(matched_table_rows) == 0:
                for table_row in pdf_table:
                    if table_row[0] in valid_tables:
                        matched_table_rows.append(table_row)

            table_text = table_to_text(
                context.real_company, context.normalized_question, matched_table_rows, with_year=False
            )
            background += table_text
            background += "\n"
            total_matched_rows.extend(matched_table_rows)

        total_matched_rows = add_text_compare_in_table(total_matched_rows)
        tot_text = table_to_text(
            context.real_company, context.normalized_question, total_matched_rows, with_year=True
        )
        return {
            "background": background,
            "tot_text": tot_text,
            "matched_rows": total_matched_rows,
        }

    @staticmethod
    def build_structured_evidence(matched_rows):
        evidence = []
        for table_name, row_year, row_name, row_value in matched_rows[:5]:
            evidence.append(
                EvidenceItem(
                    evidence_type="table_row",
                    source="structured_table",
                    content='"{}"是{}'.format(row_name, row_value),
                    year=row_year,
                    table_name=table_name,
                )
            )
        return evidence

    def load_formula_tables(self, context):
        if type2.is_type2_growth_rate(context.normalized_question):
            years_of_table = []
            for year in context.years:
                years_of_table.extend([year, str(int(year) - 1)])
            pdf_table = load_tables_of_years(context.company, years_of_table, self.pdf_tables, self.pdf_info)
            return add_growth_rate_in_table(pdf_table)

        return load_tables_of_years(context.company, context.years, self.pdf_tables, self.pdf_info)

    def retrieve_open_text_blocks(self, context, model):
        if not context.matched_pdf_names:
            return {"anoy_question": context.normalized_question, "text_blocks": []}

        anoy_question, _ = question_util.parse_question_keywords(
            model, context.normalized_question, context.real_company, context.years
        )
        text_blocks = recall_annual_report_texts(
            model,
            anoy_question,
            "".join(context.question_keywords),
            context.matched_pdf_names[0],
            None,
        )
        raw_lines = self._load_open_lines(context.matched_pdf_names[0])
        open_type = self._classify_open_question(context)
        section_blocks = []
        if open_type == "definition":
            section_blocks = self._retrieve_definition_blocks(context, raw_lines)
        else:
            section_blocks = self._retrieve_section_blocks(context, raw_lines)
        text_blocks = self._compress_open_text_blocks(context, section_blocks + text_blocks)
        return {"anoy_question": anoy_question, "text_blocks": text_blocks}

    @staticmethod
    def build_text_evidence(text_blocks):
        evidence = []
        for idx, text_block in enumerate(text_blocks[:3]):
            evidence.append(
                EvidenceItem(
                    evidence_type="text_block",
                    source="annual_report_text",
                    content=text_block,
                    year=None,
                    table_name="text_block_{}".format(idx + 1),
                )
            )
        return evidence


class StructuredQueryExecutor:
    def __init__(self):
        self.sql_cursor = get_sql_search_cursor()
        self.key_words = list(load_company_table().columns)
        self.key_word_set = set(self.key_words)

    @staticmethod
    def _normalize_sql(sql):
        if sql is None:
            return None
        sql = sql.strip().strip(";")
        sql = re.sub(r"\s+", " ", sql)
        sql = sql.replace("`", "")
        sql = re.sub(r"\s+limit\s*$", "", sql, flags=re.IGNORECASE)
        return sql

    def _validate_sql(self, sql):
        normalized_sql = self._normalize_sql(sql)
        if not normalized_sql:
            return None, "empty_sql", "SQL 为空"

        lowered = normalized_sql.lower()
        if not lowered.startswith("select"):
            return None, "sql_not_select", "仅允许执行 SELECT 查询"
        if ";" in normalized_sql:
            return None, "sql_multiple_statements", "检测到多语句 SQL，已拒绝执行"
        if any(keyword in lowered for keyword in SQL_BLOCKED_KEYWORDS):
            return None, "sql_contains_blocked_keyword", "SQL 包含非查询类关键字"

        tables = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", lowered)
        if len(tables) == 0:
            return None, "sql_missing_table", "SQL 中未识别到数据表"
        invalid_tables = [table for table in tables if table not in SQL_ALLOWED_TABLES]
        if invalid_tables:
            return None, "sql_invalid_table", "SQL 包含不允许的数据表: {}".format(",".join(invalid_tables))

        sql_fields = self._extract_sql_fields(normalized_sql)
        invalid_fields = [field for field in sql_fields if field not in self.key_word_set]
        if invalid_fields:
            return None, "sql_invalid_field", "SQL 包含未知字段: {}".format(",".join(invalid_fields))

        return normalized_sql, None, None

    @staticmethod
    def _extract_sql_fields(sql):
        fields = set()
        aliases = set(re.findall(r"\bas\s+([\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z0-9_]*)", sql, flags=re.IGNORECASE))
        sql_without_strings = re.sub(r"'[^']*'", "''", sql)
        candidate_fields = re.findall(r"[\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z0-9_（）()%]*", sql_without_strings)
        reserved_words = {
            "select", "from", "where", "and", "or", "order", "by", "desc", "asc", "limit",
            "count", "sum", "avg", "min", "max", "distinct", "as", "group", "having", "join",
            "on", "like", "is", "null", "not", "in", "case", "when", "then", "else", "end",
            "company_table",
        }
        for candidate in candidate_fields:
            stripped = candidate.strip()
            if not stripped:
                continue
            if stripped.lower() in reserved_words:
                continue
            if stripped.isdigit():
                continue
            if re.match(r"^'.*'$", stripped):
                continue
            if stripped in aliases:
                continue
            if re.search(r"[\u4e00-\u9fa5]", stripped):
                fields.add(stripped)
        return sorted(fields)

    @staticmethod
    def _execute_sql_rows(sql_cursor, sql):
        result = sql_cursor.execute(sql).fetchall()
        columns = [item[0] for item in sql_cursor.description] if sql_cursor.description else []
        return columns, result

    @staticmethod
    def _format_scalar(value):
        if isinstance(value, float):
            return "{:.2f}".format(value)
        return str(value)

    @staticmethod
    def _is_number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @staticmethod
    def _clean_answer_text(text):
        text = str(text or "").strip()
        if not text:
            return text
        text = text.replace("\n", "")
        text = re.sub(r"\s+", "", text)
        text = text.replace("；。", "。").replace("，，", "，").replace("。.", "。")
        text = re.sub(r"(\d+(?:\.\d+)?)(元|人|家)\1(?:\.\d+)?(元|人|家)", r"\1\2", text)
        text = re.sub(r"(元|人|家)\1+", r"\1", text)
        text = re.sub(r"[，；]{2,}", "；", text)
        if text and text[-1] not in "。！？":
            text += "。"
        return text

    def _detect_field_unit(self, column, question):
        column = str(column or "")
        question = str(question or "")
        if column in {"公司数量", "数量"} or re.search(r"(多少家|多少上市公司)", question):
            return "家"
        if any(token in column for token in COUNT_UNIT_HINTS):
            return "人"
        if any(token in column for token in RATIO_UNIT_HINTS):
            return "%"
        if any(token in column for token in AMOUNT_UNIT_HINTS):
            return "元"
        if "金额" in question or "数值" in question:
            return "元"
        return ""

    def _format_answer_value(self, value, column, question, force_int=False):
        unit = self._detect_field_unit(column, question)
        if value is None:
            return "未披露"
        if self._is_number(value):
            number = float(value)
            if force_int or unit in {"家", "人"}:
                rendered = str(int(round(number)))
            else:
                rendered = "{:.2f}".format(number).rstrip("0").rstrip(".")
            return "{}{}".format(rendered, unit)
        rendered = str(value).strip()
        return rendered if not unit else "{}{}".format(rendered, unit)

    def _render_row_details(self, columns, row, question):
        details = []
        for column, value in zip(columns, row):
            details.append("{}为{}".format(column, self._format_answer_value(value, column, question)))
        return "；".join(details)

    def _extract_metric_field(self, context):
        candidate_fields = []
        for field in sorted(self.key_words, key=len, reverse=True):
            if field in {"公司全称", "年份", "注册地址", "办公地址", "证券简称", "股票简称"}:
                continue
            if field in context.normalized_question or field in "".join(context.question_keywords):
                candidate_fields.append(field)
        if candidate_fields:
            return candidate_fields[0]
        for keyword in context.question_keywords:
            if keyword in self.key_word_set:
                return keyword
        return None

    @staticmethod
    def _extract_region_keyword(question):
        patterns = [
            r"注册地址在([^\d，。？?；;]+?)(?:的上市公司中|的公司中|中|，|,|并且|且)",
            r"在([^\d，。？?；;]+?)注册的(?:所有)?上市公司中",
            r"在([^\d，。？?；;]+?)注册的上市公司中",
            r"曾经在([^\d，。？?；;]+?)注册",
            r"历史注册地址在([^\d，。？?；;]+?)(?:的上市公司|的公司|中|并且|且)",
        ]
        for pattern in patterns:
            match = re.search(pattern, question)
            if match:
                region = match.group(1).strip()
                region = re.sub(r"(所有上市公司|上市公司|公司)$", "", region).strip()
                if region:
                    return region
        return None

    @staticmethod
    def _parse_rank_int(text):
        cn_map = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        if text.isdigit():
            return int(text)
        if text == "十":
            return 10
        if "十" in text:
            left, _, right = text.partition("十")
            left_val = cn_map.get(left, 1 if left == "" else 0)
            right_val = cn_map.get(right, 0)
            return left_val * 10 + right_val
        return cn_map.get(text, 1)

    def _build_fallback_sql(self, context):
        question = context.normalized_question
        metric_field = self._extract_metric_field(context)
        year = context.years[0] if context.years else None
        where_clauses = []
        if year:
            where_clauses.append("年份 = '{}'".format(year))
        region = self._extract_region_keyword(question)
        if region:
            where_clauses.append("注册地址 like '%{}%'".format(region))

        if metric_field and metric_field not in {"公司全称", "年份", "注册地址"}:
            where_clauses.append("{} is not null".format(metric_field))

        where_sql = ""
        if where_clauses:
            where_sql = " where " + " and ".join(where_clauses)

        if re.search(r"(多少家|多少上市公司)", question):
            return "select count(1) as 公司数量 from company_table{}".format(where_sql)

        if re.search(r"(平均)", question) and metric_field:
            return "select avg({0}) as 平均值 from company_table{1}".format(metric_field, where_sql)

        if re.search(r"(一共有多少|合计多少|总和)", question) and metric_field:
            return "select sum({0}) as 合计值 from company_table{1}".format(metric_field, where_sql)

        rank_match = re.search(r"第([0-9一二三四五六七八九十百两]+)[高低]", question)
        topn_match = re.search(r"前([0-9一二三四五六七八九十百两]+)家", question)
        ask_amount = bool(re.search(r"(金额|数值|是多少|为多少)", question))
        if metric_field and (rank_match or topn_match or re.search(r"(最高|最低)", question)):
            order = "desc"
            if re.search(r"(最低|低)", question):
                order = "asc"
            select_fields = ["公司全称"]
            if ask_amount:
                select_fields.append(metric_field)
            base_sql = "select {fields} from company_table{where_sql} order by {metric} {order}".format(
                fields=", ".join(select_fields),
                where_sql=where_sql,
                metric=metric_field,
                order=order,
            )
            if rank_match:
                rank_value = max(self._parse_rank_int(rank_match.group(1)), 1)
                return "{} limit 1 offset {}".format(base_sql, rank_value - 1)
            if topn_match:
                limit_value = max(self._parse_rank_int(topn_match.group(1)), 1)
                return "{} limit {}".format(base_sql, limit_value)
            return "{} limit 1".format(base_sql)

        return None

    def _format_sql_answer(self, context, columns, rows):
        if not rows:
            return ""
        question = context.original_question or context.normalized_question
        metric_field = self._extract_metric_field(context)
        if len(rows) == 1 and len(rows[0]) == 1:
            value = rows[0][0]
            if columns and columns[0] == "公司全称":
                return self._clean_answer_text("公司全称为{}。".format(str(value).strip()))
            if re.search(r"(多少家|多少上市公司)", question):
                return self._clean_answer_text("共有{}。".format(self._format_answer_value(value, "公司数量", question, force_int=True)))
            if re.search(r"(平均)", question):
                metric_name = metric_field or (columns[0] if columns else "结果")
                return self._clean_answer_text("{}平均值为{}。".format(metric_name, self._format_answer_value(value, metric_name, question)))
            if re.search(r"(一共有多少|合计多少|总和)", question):
                metric_name = metric_field or (columns[0] if columns else "结果")
                return self._clean_answer_text("{}合计为{}。".format(metric_name, self._format_answer_value(value, metric_name, question)))
            metric_name = metric_field or (columns[0] if columns else "结果")
            return self._clean_answer_text("{}为{}。".format(metric_name, self._format_answer_value(value, metric_name, question)))

        if columns and columns[0] == "公司全称":
            visible_rows = rows[:10]
            if len(visible_rows) == 1:
                company = str(visible_rows[0][0]).strip()
                if len(columns) == 1:
                    return self._clean_answer_text("答案是{}。".format(company))
                detail_parts = []
                for column, value in zip(columns[1:], visible_rows[0][1:]):
                    detail_parts.append("{}为{}".format(column, self._format_answer_value(value, column, question)))
                return self._clean_answer_text("{}，{}。".format(company, "，".join(detail_parts)))

            rendered_rows = []
            for index, row in enumerate(visible_rows, 1):
                company = str(row[0]).strip()
                detail_parts = []
                for column, value in zip(columns[1:], row[1:]):
                    detail_parts.append("{}：{}".format(column, self._format_answer_value(value, column, question)))
                if detail_parts:
                    rendered_rows.append("{}. {}（{}）".format(index, company, "，".join(detail_parts)))
                else:
                    rendered_rows.append("{}. {}".format(index, company))
            top_match = re.search(r"前([0-9一二三四五六七八九十百两]+)家", question)
            prefix = "查询结果如下"
            if top_match:
                prefix = "前{}家分别为".format(top_match.group(1))
            return self._clean_answer_text("{}：{}。".format(prefix, "；".join(rendered_rows)))

        rendered_rows = []
        for row in rows[:10]:
            rendered_rows.append(self._render_row_details(columns, row, question))
        return self._clean_answer_text("查询结果如下：{}。".format(" | ".join(rendered_rows)))

    def execute(self, context, model):
        sql = context.sql
        exec_log = ""
        attempts = []
        if sql is None:
            sql = self._build_fallback_sql(context)
            attempts.append({"strategy": "template_fallback_initial", "sql": sql})
            if sql is None:
                return None, {"sql": None, "exec_log": "sql not generated", "validation": None, "attempts": attempts}

        sql = sql.replace("总资产", "资产总计")
        sql = sql.replace("总负债", "负债合计")
        sql = sql.replace("资产总额", "资产总计")
        sql = sql.replace("其余资产", "其他流动资产")
        sql = sql.replace("公司注册地址", "注册地址")
        sql = sql.replace("历史注册地址", "注册地址")
        sql = sql_correct_util.correct_sql_number(sql, context.normalized_question)
        sql, validation_reason, validation_message = self._validate_sql(sql)
        if validation_reason is not None:
            fallback_sql = self._build_fallback_sql(context)
            attempts.append({"strategy": "validation_failed", "sql": sql, "reason": validation_reason})
            if fallback_sql and fallback_sql != sql:
                sql = fallback_sql
                attempts.append({"strategy": "template_fallback_retry", "sql": sql})
                sql, validation_reason, validation_message = self._validate_sql(sql)
            if validation_reason is not None:
                logger.warning("SQL 校验失败: {} {}".format(validation_reason, validation_message))
                return None, {
                    "sql": sql,
                    "exec_log": validation_message,
                    "validation": {
                        "status": "failed",
                        "reason": validation_reason,
                        "message": validation_message,
                    },
                    "attempts": attempts,
                }

        candidate_sqls = [("initial", sql)]
        fallback_sql = self._build_fallback_sql(context)
        if fallback_sql and fallback_sql != sql:
            candidate_sqls.append(("template_fallback", fallback_sql))

        answer = None
        final_columns = []
        final_rows = []
        last_validation = {"status": "passed"}
        for strategy, candidate_sql in candidate_sqls:
            normalized_sql, validation_reason, validation_message = self._validate_sql(candidate_sql)
            attempts.append({"strategy": strategy, "sql": candidate_sql})
            if validation_reason is not None:
                last_validation = {
                    "status": "failed",
                    "reason": validation_reason,
                    "message": validation_message,
                }
                continue
            try:
                final_columns, final_rows = self._execute_sql_rows(self.sql_cursor, normalized_sql)
                if final_rows:
                    sql = normalized_sql
                    answer = self._format_sql_answer(context, final_columns, final_rows)
                    exec_log = ""
                    break
                exec_log = "SQL 执行成功但未返回结果"
            except Exception as exc:
                exec_log = str(exc)
                logger.error("执行SQL[{}]错误! {}".format(normalized_sql.replace("<>", ""), exc))
                if "no such column" in exec_log:
                    try:
                        corrected_sql = sql_correct_util.correct_sql_field(normalized_sql, context.normalized_question, model)
                        corrected_sql, validation_reason, validation_message = self._validate_sql(corrected_sql)
                        attempts.append({"strategy": "field_correction", "sql": corrected_sql})
                        if validation_reason is None:
                            final_columns, final_rows = self._execute_sql_rows(self.sql_cursor, corrected_sql)
                            if final_rows:
                                sql = corrected_sql
                                answer = self._format_sql_answer(context, final_columns, final_rows)
                                exec_log = ""
                                break
                    except Exception as inner_exc:
                        logger.error("字段纠正失败: {}".format(inner_exc))

        return answer, {
            "sql": sql,
            "exec_log": exec_log,
            "validation": last_validation if answer is None else {"status": "passed"},
            "attempts": attempts,
            "columns": final_columns,
            "row_count": len(final_rows),
            "rows_preview": [list(map(self._format_scalar, row)) for row in final_rows[:5]],
        }


class AnswerSynthesizer:
    def __init__(self, model, retriever, sql_executor):
        self.model = model
        self.retriever = retriever
        self.sql_executor = sql_executor

    @staticmethod
    def _clean_structured_answer_text(text):
        text = str(text or "").strip()
        if not text:
            return text
        text = text.replace("\n", "")
        text = re.sub(r"\s+", "", text)
        text = text.replace("\"", "")
        text = text.replace(",", "，")
        text = text.replace("不相同且不同", "不相同")
        text = text.replace("相同且一致", "相同")
        text = re.sub(r"([0-9]{4})与([0-9]{4})相比年的", r"\1年与\2年相比，", text)
        text = re.sub(r"[，；]{2,}", "，", text)
        text = re.sub(r"(\d+(?:\.\d+)?)(元|人|家)\1(?:\.\d+)?(元|人|家)", r"\1\2", text)
        text = re.sub(r"(元|人|家)\1+", r"\1", text)
        if text and text[-1] not in "。！？":
            text += "。"
        return text

    @staticmethod
    def _normalize_comparison_answer(text):
        matches = re.findall(r"([0-9]{4})年的([^是，。]+)是[\"“]?([^\"”，。]+)", text)
        if len(matches) < 2:
            return text
        attribute = matches[0][1]
        year_values = []
        for year, attr, value in matches:
            if attr != attribute:
                return text
            year_values.append((year, value.strip("，。")))
        summary = "相同" if len({value for _, value in year_values}) == 1 else "不相同"
        return "，".join("{}年{}为{}".format(year, attribute, value) for year, value in year_values) + "，两年{}。".format(summary)

    @staticmethod
    def _clean_open_answer_text(text):
        text = str(text or "").strip()
        if not text:
            return text
        text = text.replace("\r", "").strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"^[0-9]+\.\s*", "", text)
        text = re.sub(r"\n[0-9]+\.\s*", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"(根据查询|经查询|根据提供资料|根据年报片段)", "", text)
        return text.strip()

    def _build_open_question_prompt(self, context, text_blocks):
        answer_style = "请用2-4句中文短段落作答。"
        if re.search(r"(什么是|是指什么|定义)", context.normalized_question):
            answer_style = "请先给出一句定义，再补充1-2句关键特征，总共不超过4句。"
        elif re.search(r"(简要介绍|概述|详情|情况)", context.normalized_question):
            answer_style = "请围绕问题直接总结关键事实，优先写事项内容、原因、影响，总共不超过5句。"

        evidence_lines = []
        for idx, block in enumerate(text_blocks[:3], 1):
            evidence_lines.append("证据{}：{}".format(idx, block))

        return (
            "你是金融年报问答助手。请严格只依据下面给出的年报证据回答，不要补充常识，不要扩写无关背景。\n"
            "如果证据不足以直接回答，就明确回答“年报片段中未明确披露”。\n"
            "{}\n"
            "输出要求：\n"
            "1. 不要分点编号。\n"
            "2. 不要复述题目。\n"
            "3. 不要写“根据资料/根据查询”。\n"
            "4. 只保留和问题直接相关的信息。\n\n"
            "{}\n\n"
            "问题：{}\n"
            "答案："
        ).format(answer_style, "\n".join(evidence_lines), context.original_question)

    def answer_structured_question(self, context):
        if not context.company_abbrs:
            logger.warning("匹配到了类别{}, 但是不存在报表".format(context.question_type))
            return None, {"matched_rows": 0}, [], "no_matched_company", "没有匹配到公司年报"

        logger.info("问题关键词: {}".format(context.question_keywords))
        retrieved = self.retriever.retrieve_structured_background(context)
        evidence = self.retriever.build_structured_evidence(retrieved["matched_rows"])
        if len(evidence) == 0:
            return None, {"matched_rows": 0}, [], "evidence_insufficient", "未找到可用的结构化证据"
        if "相同" in retrieved["tot_text"] or "不相同且不同" in retrieved["tot_text"]:
            answer = self._normalize_comparison_answer(retrieved["tot_text"])
            answer = self._clean_structured_answer_text(answer)
            return answer, {"matched_rows": len(retrieved["matched_rows"])}, evidence, None, None

        question_for_model = type1.get_prompt(
            context.normalized_question, context.company, context.abbr, context.years
        ).format(retrieved["background"], context.normalized_question)
        logger.info("Prompt length {}".format(len(question_for_model)))
        if len(question_for_model) > 5120:
            question_for_model = question_for_model[:5120]
        logger.info(question_for_model.replace("<", ""))
        answer = self.model(question_for_model)
        answer = self._clean_structured_answer_text(answer)
        logger.opt(colors=True).info("<magenta>{}</>".format(answer.replace("<", "")))
        return answer, {"matched_rows": len(retrieved["matched_rows"])}, evidence, None, None

    def answer_formula_question(self, context):
        if not context.company_abbrs:
            logger.warning("匹配到了类别{}, 但是不存在报表".format(context.question_type))
            return None, {"step_count": 0}, [], "no_matched_company", "没有匹配到公司年报"

        logger.info("问题关键词: {}".format(context.question_keywords))
        pdf_table = self.retriever.load_formula_tables(context)
        step_questions, step_keywords, variable_names, step_years, formula, question_formula = type2.get_step_questions(
            context.normalized_question,
            "".join(context.question_keywords),
            context.real_company,
            context.years[0],
        )

        step_answers = []
        variable_values = []
        evidence = []
        for step_question, step_keyword, step_year in zip(step_questions, step_keywords, step_years):
            if len(step_keyword) == 0:
                logger.error("关键词为空")

            background = "已知{}{}年的资料如下:\n".format(context.real_company, step_year)
            matched_table_rows = recall_pdf_tables(
                step_keyword,
                [step_year],
                pdf_table,
                min_match_number=3,
                top_k=5,
            )
            if len(matched_table_rows) == 0:
                logger.warning("无法匹配keyword {}, 尝试不设置限制".format(step_keyword))
                matched_table_rows = recall_pdf_tables(
                    step_keyword,
                    [step_year],
                    pdf_table,
                    min_match_number=2,
                    top_k=None,
                )
            if len(matched_table_rows) == 0:
                logger.error("仍然无法匹配keyword {}".format(step_keyword))
                matched_table_rows = recall_pdf_tables(
                    step_keyword,
                    [step_year],
                    pdf_table,
                    min_match_number=0,
                    top_k=10,
                )
            evidence.extend(self.retriever.build_structured_evidence(matched_table_rows))

            table_text = table_to_text(
                context.real_company,
                context.normalized_question,
                matched_table_rows,
                with_year=False,
            )
            if table_text != "":
                background += table_text

            question_for_model = get_prompt_single_question(
                context.normalized_question, context.real_company, step_year
            ).format(background, step_question)
            logger.opt(colors=True).info("<cyan>{}</>".format(question_for_model.replace("<", "")))
            step_answer = self.model(question_for_model)
            variable_value = type2.get_variable_value_from_answer(step_answer)
            if variable_value is not None:
                step_answers.append(step_answer)
                variable_values.append(variable_value)
            logger.opt(colors=True).info(
                "<green>{}</><red>{}</>".format(step_answer.replace("<", ""), variable_value)
            )

        answer = None
        if len(step_questions) == len(variable_values):
            for name, value in zip(variable_names, variable_values):
                formula = formula.replace(name, value)
            try:
                result = eval(formula)
            except Exception:
                logger.error("Eval formula {} failed".format(formula))
                result = None
            if result is not None:
                numeric_answer = "{:.2f}".format(result)
                if "率" in context.normalized_question or "比例" in context.normalized_question or "%" in question_formula:
                    answer = "{}的结果为{}（{}%）。".format(context.original_question.replace("？", ""), numeric_answer, "{:.2f}".format(result * 100))
                else:
                    answer = "{}的结果为{}。".format(context.original_question.replace("？", ""), numeric_answer)
                answer = self._clean_structured_answer_text(answer)
                logger.opt(colors=True).info("<magenta>{}</>".format(answer.replace("<", "")))

        failure_reason = None
        error_message = None
        if answer is None:
            failure_reason = "evidence_insufficient"
            error_message = "计算链路未能提取足够变量"
        return answer, {"step_count": len(step_questions), "formula": question_formula}, evidence[:5], failure_reason, error_message

    def answer_sql_question(self, context):
        logger.info("这是个统计题")
        answer, sql_trace = self.sql_executor.execute(context, self.model)
        evidence = []
        if sql_trace["sql"] is not None:
            evidence.append(
                EvidenceItem(
                    evidence_type="sql",
                    source="company_table",
                    content=sql_trace["sql"],
                    year=context.years[0] if context.years else None,
                    table_name="company_table",
                )
            )
        for row in sql_trace.get("rows_preview", [])[:3]:
            evidence.append(
                EvidenceItem(
                    evidence_type="sql_result",
                    source="company_table",
                    content=" | ".join(row),
                    year=context.years[0] if context.years else None,
                    table_name="company_table",
                )
            )
        if sql_trace["sql"] is not None:
            logger.opt(colors=True).info("<green>{}</>".format(sql_trace["sql"].replace("<>", "")))
        logger.opt(colors=True).info("<magenta>{}</>".format(str(answer).replace("<>", "")))
        failure_reason = None
        error_message = None
        if answer is None:
            failure_reason = "sql_failed"
            error_message = sql_trace.get("exec_log", "SQL 执行失败")
        return answer, sql_trace, evidence, failure_reason, error_message

    def answer_open_question(self, context):
        if len(context.years) == 0:
            logger.warning("匹配到Type3-2")
            prompt = (
                "你是金融知识问答助手。请直接回答问题，不要分点，不要展开无关背景，控制在4句以内。\n"
                "问题：{}\n答案："
            ).format(context.original_question)
            answer = self.model(prompt)
            answer = self._clean_open_answer_text(answer)
            logger.opt(colors=True).info("<magenta>{}</>".format(answer.replace("<", "")))
            return answer, {"text_block_count": 0}, [], None, None

        if len(context.company_abbrs) == 0:
            logger.warning("问题存在年份, 但没有匹配的年报")
            return None, {"text_block_count": 0}, [], "no_matched_company", "问题包含年份，但没有匹配到对应公司年报"

        logger.info("问题关键词: {}".format(context.question_keywords))
        retrieved = self.retriever.retrieve_open_text_blocks(context, self.model)
        evidence = self.retriever.build_text_evidence(retrieved["text_blocks"])
        if len(retrieved["text_blocks"]) == 0:
            return None, {"text_block_count": 0}, [], "evidence_insufficient", "未召回到相关年报文本片段"
        question_for_model = self._build_open_question_prompt(context, retrieved["text_blocks"])
        logger.info("Prompt length {}".format(len(question_for_model)))
        if len(question_for_model) > 5120:
            question_for_model = question_for_model[:5120]
        logger.info(question_for_model.replace("<", ""))
        answer = self.model(question_for_model)
        answer = self._clean_open_answer_text(answer)
        logger.info("Answer length {}".format(len(answer)))
        logger.opt(colors=True).info("<magenta>{}</>".format(answer.replace("<", "")))
        return answer, {"text_block_count": len(retrieved["text_blocks"])}, evidence, None, None


class FinancialAnnualReportWorkflow:
    def __init__(self, model):
        self.model = model
        self.pdf_info = load_pdf_info()
        self.pdf_tables = load_total_tables()
        self.test_questions = load_test_questions()
        self.router = QueryRouter(self.pdf_info)
        self.retriever = DocumentEvidenceRetriever(self.pdf_info, self.pdf_tables)
        self.sql_executor = StructuredQueryExecutor()
        self.synthesizer = AnswerSynthesizer(model, self.retriever, self.sql_executor)
        self.trace_dir = os.path.join(cfg.DATA_PATH, "workflow")
        if not os.path.exists(self.trace_dir):
            os.mkdir(self.trace_dir)

    def answer_question(self, question, runtime_artifacts=None):
        return self.run_question(question, runtime_artifacts=runtime_artifacts).answer

    def run_question(self, question, runtime_artifacts=None):
        started_at = perf_counter()
        context = self.router.build_context(question, runtime_artifacts=runtime_artifacts)
        answer = DEFAULT_ANSWER_TEMPLATE.format(context.normalized_question)
        route_trace = {}
        evidence = []
        failure_reason = None
        error_message = None

        logger.opt(colors=True).info(
            "<blue>Start process question {} {}</>".format(
                context.question_id, context.original_question.replace("<", "")
            )
        )
        logger.opt(colors=True).info("<cyan>问题类型{}</>".format(context.question_type.replace("<", "")))
        logger.info("执行路径: {}".format(" -> ".join(context.execution_path)))

        try:
            route_started_at = perf_counter()
            if context.question_type in STRUCTURED_ROUTE_TYPES:
                answer, route_trace, evidence, failure_reason, error_message = self.synthesizer.answer_structured_question(context)
            elif context.question_type == "D":
                answer, route_trace, evidence, failure_reason, error_message = self.synthesizer.answer_formula_question(context)
            elif context.question_type == "E":
                answer, route_trace, evidence, failure_reason, error_message = self.synthesizer.answer_sql_question(context)
            elif context.question_type == "F":
                answer, route_trace, evidence, failure_reason, error_message = self.synthesizer.answer_open_question(context)
            route_trace["timings"] = {
                "synthesis_ms": round((perf_counter() - route_started_at) * 1000, 2),
            }
        except Exception as exc:
            logger.exception("处理问题 {} 失败: {}", context.question_id, exc)
            failure_reason = "internal_error"
            error_message = str(exc)

        if answer is None:
            logger.error("问题无法找到类别, 无法回答")
            answer = ""
        success = len(answer) > 0 and failure_reason is None
        status = "success" if success else "failed"
        route_trace.setdefault("timings", {})
        route_trace["timings"]["total_workflow_ms"] = round((perf_counter() - started_at) * 1000, 2)

        result = WorkflowResult(
            success=success,
            status=status,
            answer=answer,
            question_type=context.question_type,
            route_name=context.route_name,
            route_label=context.route_label,
            output_type=context.output_type,
            execution_path=context.execution_path,
            question_keywords=context.question_keywords,
            failure_reason=failure_reason,
            error_message=error_message,
            evidence=evidence,
            route_trace=route_trace,
            context=context,
        )
        self._save_trace(result)
        return result

    def _save_trace(self, result):
        trace = {
            "project_name": PROJECT_NAME,
            "project_subtitle": PROJECT_SUBTITLE,
            "project_description": PROJECT_DESCRIPTION,
            "question_id": result.context.question_id,
            "question_type": result.question_type,
            "route_name": result.route_name,
            "route_label": result.route_label,
            "output_type": result.output_type,
            "execution_path": result.execution_path,
            "question_keywords": result.question_keywords,
            "status": result.status,
            "success": result.success,
            "failure_reason": result.failure_reason,
            "error_message": result.error_message,
            "target_architecture_code_map": TARGET_ARCHITECTURE_CODE_MAP,
            "prompt_versions": get_prompt_version_snapshot(),
            "context": asdict(result.context),
            "route_trace": result.route_trace,
            "evidence": [asdict(item) for item in result.evidence],
            "answer_preview": result.answer[:500] if result.answer else "",
        }
        trace_path = os.path.join(self.trace_dir, "{}.json".format(result.context.question_id))
        with open(trace_path, "w", encoding="utf-8") as file_obj:
            json.dump(trace, file_obj, ensure_ascii=False, indent=2)
