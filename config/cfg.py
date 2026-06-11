import os

PDF_TEXT_DIR = "pdf_docs"
ERROR_PDF_DIR = "error_pdfs"
CLASSIFY_PTUNING_PRE_SEQ_LEN = 512
KEYWORDS_PTUNING_PRE_SEQ_LEN = 256
NL2SQL_PTUNING_PRE_SEQ_LEN = 128
NL2SQL_PTUNING_MAX_LENGTH = 2200

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..")) + os.sep
DATA_PATH = os.path.join(BASE_DIR, "data") + os.sep
NUM_PROCESSES = int(os.getenv("NUM_PROCESSES", "64"))


def _resolve_env_path(path_value):
    if not path_value:
        return None
    if os.path.isabs(path_value):
        return path_value
    return os.path.abspath(os.path.join(BASE_DIR, path_value))


def _env_candidates():
    explicit_path = _resolve_env_path(os.getenv("ANNUAL_REPORT_AGENT_ENV_FILE", "").strip())
    default_path = os.path.join(BASE_DIR, ".env")
    candidates = []
    for path in [explicit_path, default_path]:
        if path and path not in candidates:
            candidates.append(path)
    return candidates


def _load_dotenv():
    for env_path in _env_candidates():
        if not os.path.exists(env_path):
            continue
        with open(env_path, "r", encoding="utf-8") as file_obj:
            for raw_line in file_obj:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value


_load_dotenv()

CLASSIFY_CHECKPOINT_PATH = os.path.join(
    BASE_DIR,
    "ptuning/CLASSIFY_PTUNING/output/Fin-Train-chatglm2-6b-pt-512-2e-2/checkpoint-400",
)
NL2SQL_CHECKPOINT_PATH = os.path.join(
    BASE_DIR,
    "ptuning/NL2SQL_PTUNING/output/Fin-Train-chatglm2-6b-pt-128-2e-2/checkpoint-600",
)
KEYWORDS_CHECKPOINT_PATH = os.path.join(
    BASE_DIR,
    "ptuning/KEYWORDS_PTUNING/output/Fin-Train-chatglm2-6b-pt-256-2e-2/checkpoint-250",
)
XPDF_PATH = os.getenv(
    "ANNUAL_REPORT_AGENT_XPDF_PATH",
    os.getenv("XPDF_PATH", os.path.join(BASE_DIR, "xpdf", "bin64")),
)
LLM_MODEL_DIR = os.getenv(
    "LLM_MODEL_DIR",
    os.path.join(DATA_PATH, "pretrained_models/chatglm2-6b"),
)

# OpenAI-compatible API config. SiliconFlow is the default provider.
LLM_API_BASE_URL = os.getenv(
    "LLM_API_BASE_URL",
    os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
).rstrip("/")
LLM_API_ENDPOINT = os.getenv("LLM_API_ENDPOINT", "/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("SILICONFLOW_API_KEY", ""))
LLM_API_TIMEOUT = int(os.getenv("LLM_API_TIMEOUT", "60"))
LLM_API_TEMPERATURE = float(os.getenv("LLM_API_TEMPERATURE", "0"))

LLM_API_DEFAULT_MODEL = os.getenv("LLM_API_MODEL", os.getenv("SILICONFLOW_MODEL", ""))
LLM_API_CLASSIFY_MODEL = os.getenv(
    "LLM_API_CLASSIFY_MODEL",
    os.getenv("SILICONFLOW_CLASSIFY_MODEL", LLM_API_DEFAULT_MODEL),
)
LLM_API_KEYWORDS_MODEL = os.getenv(
    "LLM_API_KEYWORDS_MODEL",
    os.getenv("SILICONFLOW_KEYWORDS_MODEL", LLM_API_DEFAULT_MODEL),
)
LLM_API_NL2SQL_MODEL = os.getenv(
    "LLM_API_NL2SQL_MODEL",
    os.getenv("SILICONFLOW_NL2SQL_MODEL", LLM_API_DEFAULT_MODEL),
)
LLM_API_ANSWER_MODEL = os.getenv(
    "LLM_API_ANSWER_MODEL",
    os.getenv("SILICONFLOW_ANSWER_MODEL", LLM_API_DEFAULT_MODEL),
)


def get_api_model(task_name):
    mapping = {
        "classify": LLM_API_CLASSIFY_MODEL,
        "keywords": LLM_API_KEYWORDS_MODEL,
        "nl2sql": LLM_API_NL2SQL_MODEL,
        "answer": LLM_API_ANSWER_MODEL,
    }
    model_name = mapping.get(task_name, LLM_API_DEFAULT_MODEL)
    if not model_name:
        raise RuntimeError(
            "LLM API model is not configured. Set `LLM_API_MODEL` or task-specific model env vars."
        )
    return model_name
