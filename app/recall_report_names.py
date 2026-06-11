import re
from difflib import SequenceMatcher
from loguru import logger
from config import cfg

'''
用于从PDF表格数据中召回与给定关键词匹配的行数据

keywords：待匹配的关键词（字符串）
years：目标年份列表（如 ["2022", "2021"]）
tables：原始表格数据（结构化为 [表名, 年份, 行名, 行值] 的列表）
valid_tables/invalid_tables：允许/禁止的表名过滤列表
min_match_number：最小连续匹配字符数（默认3）
top_k：返回的最大结果数
'''
def recall_pdf_tables(keywords, years, tables, valid_tables=None, invalid_tables=None, 
        min_match_number=3, top_k=None):
    logger.info('recall words {}'.format(keywords))
    
    # 保留原始关键词副本
    valid_keywords = keywords
    # 存储匹配结果
    matched_lines = []
    for table_row in tables:
        # 解析表格行数据
        table_name, row_year, row_name, row_value = table_row
        # 清理噪声字符
        row_name = row_name.replace('"', '')
        # 1. 年份过滤
        if row_year not in years:
            continue
        # 2. 表名过滤
        if valid_tables is not None and table_name not in valid_tables:
            continue
        
        if invalid_tables is not None and table_name in invalid_tables:
            continue
        # 3. 精确匹配（最高优先级）
        # find exact match, only return this row
        if row_name == valid_keywords:
            matched_lines = [(table_row, len(row_name))]
            break
        # 4. 模糊匹配
        tot_match_size = 0
        matches = SequenceMatcher(None, valid_keywords, row_name, autojunk=False)
        for match in matches.get_matching_blocks():
            inter_text = valid_keywords[match.a:match.a+match.size]
            tot_match_size += match.size
        # 5. 条件判断
        if tot_match_size >= min_match_number or row_name in valid_keywords:
            matched_lines.append([table_row, tot_match_size])

    matched_lines = sorted(matched_lines, key=lambda x: x[1], reverse=True)
    matched_lines = [t[0] for t in matched_lines]
    if top_k is not None and len(matched_lines) > top_k:
        matched_lines = matched_lines[:top_k]
    return matched_lines


if __name__ == '__main__':
    from file import load_pdf_info
    from file import load_embedding
    from file import load_test_questions

    
    pdf_info = load_pdf_info()
    test_questions = load_test_questions()

    for question in test_questions[:3000]:
        recall_extact_match(question['question'], pdf_info)
