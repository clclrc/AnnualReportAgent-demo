from . import prompt_util


PROMPT_REGISTRY_VERSION = "2026-04-14.v1"

PROMPT_REGISTRY = {
    "classify_router": {
        "version": "v1",
        "owner": "api_llm.ApiLLM._get_classify_prompt",
        "purpose": "问题分类与路由",
    },
    "keyword_extract": {
        "version": "v1",
        "owner": "prompt_util.prompt_get_key_word",
        "purpose": "关键词提取",
        "template": prompt_util.prompt_get_key_word,
    },
    "open_qa": {
        "version": "v1",
        "owner": "prompt_util.prompt_question_tp31",
        "purpose": "开放问答总结",
        "template": prompt_util.prompt_question_tp31,
    },
    "single_step_formula": {
        "version": "v1",
        "owner": "prompt_util.get_prompt_single_question",
        "purpose": "计算链路分步问答",
    },
    "sql_correct": {
        "version": "v1",
        "owner": "prompt_util.prompt_sql_correct",
        "purpose": "SQL 修正",
        "template": prompt_util.prompt_sql_correct,
    },
}


def get_prompt_version_snapshot():
    return {
        "registry_version": PROMPT_REGISTRY_VERSION,
        "prompts": {
            name: {
                "version": meta["version"],
                "owner": meta["owner"],
                "purpose": meta["purpose"],
            }
            for name, meta in PROMPT_REGISTRY.items()
        },
    }

