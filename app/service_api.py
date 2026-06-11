import json
import re
from functools import lru_cache
from time import perf_counter
from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .api_llm import ApiLLM, TaskType
from .company_table import load_company_table
from .financial_agent_workflow import FinancialAnnualReportWorkflow
from .project_meta import PROJECT_DESCRIPTION
from .project_meta import PROJECT_NAME
from .project_meta import PROJECT_SUBTITLE
from . import question_util


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class QueryRequest(BaseModel):
    question: str = Field(..., description="用户问题")
    question_id: Optional[int] = Field(default=-1, description="可选问题 ID")


class EvidenceResponse(BaseModel):
    evidence_type: str
    source: str
    content: str
    year: Optional[str] = None
    table_name: Optional[str] = None


class QueryResponse(BaseModel):
    project_name: str
    project_subtitle: str
    success: bool
    status: str
    question_id: int
    question: str
    answer: str
    question_type: str
    route_name: str
    route_label: str
    output_type: str
    execution_path: List[str]
    question_keywords: List[str]
    evidence: List[EvidenceResponse]
    failure_reason: Optional[str] = None
    error_message: Optional[str] = None
    route_trace: dict
    context: dict


class StreamChunk(BaseModel):
    event: str
    data: dict


app = FastAPI(
    title=PROJECT_NAME,
    summary=PROJECT_SUBTITLE,
    description=PROJECT_DESCRIPTION,
)


def _build_response(result, request: QueryRequest) -> QueryResponse:
    return QueryResponse(
        project_name=PROJECT_NAME,
        project_subtitle=PROJECT_SUBTITLE,
        success=result.success,
        status=result.status,
        question_id=result.context.question_id,
        question=request.question,
        answer=result.answer,
        question_type=result.question_type,
        route_name=result.route_name,
        route_label=result.route_label,
        output_type=result.output_type,
        execution_path=result.execution_path,
        question_keywords=result.question_keywords,
        evidence=[EvidenceResponse(**item.__dict__) for item in result.evidence],
        failure_reason=result.failure_reason,
        error_message=result.error_message,
        route_trace=result.route_trace,
        context=result.context.__dict__,
    )


def _classify_question(classify_model, question: str) -> str:
    result = classify_model.classify(question)
    if re.findall(r"(状况|简要介绍|简要分析|概述|具体描述|审计意见)", question):
        result = "F"
    if re.findall(r"(什么是|指什么|什么意思|定义|含义|为什么)", question):
        result = "F"
    return result


def _is_statistical_question(question: str) -> bool:
    return bool(
        re.search(
            r"(第[0-9一二三四五六七八九十百]+[高低]|前[0-9一二三四五六七八九十百]+家|最高|最低|多少家|多少上市公司|平均|总和|合计多少|一共有多少|排名|top\s*[0-9]+)",
            question,
            flags=re.IGNORECASE,
        )
    )


@lru_cache(maxsize=1)
def _company_table_columns():
    return list(load_company_table().columns)


@lru_cache(maxsize=1)
def _shared_workflow():
    return FinancialAnnualReportWorkflow(ApiLLM(TaskType.Nothing))


@lru_cache(maxsize=None)
def _shared_model(task_value: str):
    return ApiLLM(TaskType(task_value))


def _normalize_keywords(question: str, question_type: str, raw_keywords: List[str], workflow) -> List[str]:
    cleaned_keywords = []
    question_no_year = re.sub(r"20\d{2}年?", " ", question)
    company_terms = set(question_util.get_match_company_names(question, workflow.pdf_info))
    table_columns = _company_table_columns()
    table_columns_sorted = sorted(table_columns, key=len, reverse=True)

    for raw_keyword in raw_keywords:
        candidate = raw_keyword.strip()
        if not candidate:
            continue
        candidate = candidate.replace("，", ",")
        candidate = re.sub(r"\s+", " ", candidate)
        for company_term in company_terms:
            candidate = candidate.replace(company_term, " ")
        candidate = re.sub(r"20\d{2}年?", " ", candidate)
        candidate = re.sub(r"(请告诉我|请提供|具体情况|具体数值|详细数据|是多少|为多少|是什么|情况)", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,")
        if candidate:
            cleaned_keywords.append(candidate)

    extracted_columns = []
    source_texts = cleaned_keywords + [question_no_year]
    for source_text in source_texts:
        for column in table_columns_sorted:
            if column in source_text and column not in extracted_columns:
                extracted_columns.append(column)

    if question_type in {"A", "B", "C", "D", "G"} and extracted_columns:
        return extracted_columns[:3]
    if question_type == "E" and extracted_columns:
        return extracted_columns[:5]

    deduped = []
    for keyword in cleaned_keywords:
        if keyword and keyword not in deduped:
            deduped.append(keyword)
    return deduped[:5] if deduped else [question]


def _runtime_artifacts(question_id: int, question: str):
    classify_model = _shared_model(TaskType.Classify.value)
    keywords_model = _shared_model(TaskType.Keywords.value)
    nl2sql_model = _shared_model(TaskType.NL2SQL.value)
    workflow = _shared_workflow()
    matched_companies = question_util.get_match_company_names(question, workflow.pdf_info)
    question_type = _classify_question(classify_model, question)
    if _is_statistical_question(question):
        question_type = "E"
    if question_type in ["A", "B", "C", "D"] and len(matched_companies) == 0:
        question_type = "F"
    if question_type == "E" and len(matched_companies) > 0 and not _is_statistical_question(question):
        question_type = "G"

    keywords = keywords_model.keywords(question)
    keyword_list = [item.strip() for item in keywords.replace("，", ",").split(",") if item.strip()]
    if len(keyword_list) == 0:
        keyword_list = [question]
    keyword_list = _normalize_keywords(question, question_type, keyword_list, workflow)

    sql = None
    if question_type == "E":
        sql = nl2sql_model.nl2sql(question)

    return {
        "class": question_type,
        "keywords": keyword_list,
        "sql": sql,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "project_name": PROJECT_NAME,
        "project_subtitle": PROJECT_SUBTITLE,
    }


@app.post("/v1/query", response_model=QueryResponse)
def query(request: QueryRequest):
    total_started_at = perf_counter()
    workflow = _shared_workflow()
    question = {"id": request.question_id if request.question_id is not None else -1, "question": request.question}
    runtime_started_at = perf_counter()
    runtime_artifacts = _runtime_artifacts(question["id"], request.question)
    runtime_elapsed_ms = round((perf_counter() - runtime_started_at) * 1000, 2)
    workflow_started_at = perf_counter()
    result = workflow.run_question(question, runtime_artifacts=runtime_artifacts)
    workflow_elapsed_ms = round((perf_counter() - workflow_started_at) * 1000, 2)
    result.route_trace["performance"] = {
        "runtime_artifacts_ms": runtime_elapsed_ms,
        "workflow_ms": workflow_elapsed_ms,
        "total_ms": round((perf_counter() - total_started_at) * 1000, 2),
    }
    workflow._save_trace(result)
    return _build_response(result, request)


@app.post("/v1/query/stream")
def query_stream(request: QueryRequest):
    def event_stream():
        total_started_at = perf_counter()
        workflow = _shared_workflow()
        question = {"id": request.question_id if request.question_id is not None else -1, "question": request.question}
        runtime_started_at = perf_counter()
        runtime_artifacts = _runtime_artifacts(question["id"], request.question)
        runtime_elapsed_ms = round((perf_counter() - runtime_started_at) * 1000, 2)
        workflow_started_at = perf_counter()
        result = workflow.run_question(question, runtime_artifacts=runtime_artifacts)
        workflow_elapsed_ms = round((perf_counter() - workflow_started_at) * 1000, 2)
        result.route_trace["performance"] = {
            "runtime_artifacts_ms": runtime_elapsed_ms,
            "workflow_ms": workflow_elapsed_ms,
            "total_ms": round((perf_counter() - total_started_at) * 1000, 2),
        }
        workflow._save_trace(result)

        start_chunk = StreamChunk(
            event="start",
            data={
                "question_id": result.context.question_id,
                "question": request.question,
                "project_name": PROJECT_NAME,
            },
        )
        yield json.dumps(_model_to_dict(start_chunk), ensure_ascii=False) + "\n"

        route_chunk = StreamChunk(
            event="route",
            data={
                "question_type": result.question_type,
                "route_name": result.route_name,
                "execution_path": result.execution_path,
                "question_keywords": result.question_keywords,
            },
        )
        yield json.dumps(_model_to_dict(route_chunk), ensure_ascii=False) + "\n"

        evidence_chunk = StreamChunk(
            event="evidence",
            data={
                "evidence": [item.__dict__ for item in result.evidence],
            },
        )
        yield json.dumps(_model_to_dict(evidence_chunk), ensure_ascii=False) + "\n"

        result_chunk = StreamChunk(
            event="result",
            data=_model_to_dict(_build_response(result, request)),
        )
        yield json.dumps(_model_to_dict(result_chunk), ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
