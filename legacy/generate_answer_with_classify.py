import os
import json
import copy
import parse
import re
from itertools import chain
from loguru import logger
from datetime import datetime

from app import re_util
from config import cfg
from app.file import load_total_tables
from app.file import load_tables_of_years
from app.file import add_growth_rate_in_table
from app.file import table_to_text, add_text_compare_in_table
from app.file import load_pdf_info, load_test_questions
from app.company_table import get_sql_search_cursor, load_company_table
from app.recall_report_text import recall_annual_report_texts
from app.recall_report_names import recall_pdf_tables
from app import type2, type1
from app import prompt_util
from app import question_util
from app import sql_correct_util
from app.financial_agent_workflow import FinancialAnnualReportWorkflow

'''
对测试集问题进行分类，并将结果保存到csv文件中。
'''
def do_classification(model):
    logger.info('Do classfication...')
    # 加载测试问题集
    test_questions = load_test_questions()  
    # 加载 PDF 信息
    pdf_info = load_pdf_info()
    # 构建分类结果保存路径
    classify_dir = os.path.join(cfg.DATA_PATH, 'classify')
    # 检查目录是否存在
    if not os.path.exists(classify_dir):
        os.mkdir(classify_dir)
    # 遍历每一个问题
    for question in test_questions:
        # 生成结果文件路径
        class_csv = os.path.join(classify_dir, '{}.csv'.format(question['id']))
        # 匹配问题中的公司名称
        mactched_comp_names = question_util.get_match_company_names(question['question'], pdf_info)

        # 带颜色的日志输出
        logger.opt(colors=True).info('<blue>Start process question {} {}</>'.format(question['id'], question['question']))
        # 将问题输入模型，得到模型的输出结果
        result = model.classify(question['question'])
        
        # 规则1：若问题包含特定关键词，强制设为 F 类
        if re.findall('(状况|简要介绍|简要分析|概述|具体描述|审计意见)', question['question']):
            result = 'F'
        
        # 规则2：若问题包含定义类关键词，强制设为 F 类
        if re.findall('(什么是|指什么|什么意思|定义|含义|为什么)', question['question']):
            result = 'F'

        # 规则3：若结果为 A-D 但未匹配到公司，改为 F 类
        if result in ['A', 'B', 'C', 'D'] and len(mactched_comp_names) == 0:
            logger.info('AAAA{}'.format(question['question']))
            result = 'F'
        
        # 规则4：若结果为 E 但匹配到公司，改为 G 类
        if result in ['E'] and len(mactched_comp_names) > 0:
            logger.info('BBBBB{}'.format(question['question']))
            result = 'G'

        # 清理结果中的 < 字符
        logger.info(result.replace('<', ''))

        with open(class_csv, 'w', encoding='utf-8') as f:
            save_result = copy.deepcopy(question)   # 深拷贝原始问题数据
            save_result['class'] = result    # 添加分类结果字段

            json.dump(save_result, f, ensure_ascii=False)   # 以 JSON 格式写入 CSV 文件

'''
生成测试集的关键词，并保存到csv文件中
'''
def do_gen_keywords(model):
    # 记录关键词生成任务开始日志
    logger.info('Do gen keywords...')
    # 加载测试问题集
    test_questions = load_test_questions()

    pdf_info = load_pdf_info()
    
    # 构建关键词结果保存路径
    keywords_dir = os.path.join(cfg.DATA_PATH, 'keywords')
    if not os.path.exists(keywords_dir):
        os.mkdir(keywords_dir)
    # 遍历每个问题
    for question in test_questions:
        keywords_csv = os.path.join(keywords_dir, '{}.csv'.format(question['id']))
        logger.opt(colors=True).info('<blue>Start process question {} {}</>'.format(question['id'], question['question']))
        # 生成关键词并分割为列表
        result = model.keywords(question['question']).split(',')
        # 记录原始结果
        logger.info(result)
        # 写入文件
        with open(keywords_csv, 'w', encoding='utf-8') as f:
            save_result = copy.deepcopy(question)
            if len(result) == 0:
                logger.warning('问题{}的关键词为空'.format(question['question']))
                result = [question['question']]
            save_result['keywords'] = result

            json.dump(save_result, f, ensure_ascii=False)


'''
为测试集问题生成sql语句。
'''
def do_sql_generation(model):
    logger.info('Do sql generation...')
    test_questions = load_test_questions()

    sql_dir = os.path.join(cfg.DATA_PATH, 'sql')
    if not os.path.exists(sql_dir):
        os.mkdir(sql_dir)
    # 遍历每一个问题
    for question in test_questions:

        sql_csv = os.path.join(sql_dir, '{}.csv'.format(question['id']))
        # 初始化sql为空
        sql = None

        # 分类结果检查
        class_csv = os.path.join(cfg.DATA_PATH, 'classify', '{}.csv'.format(question['id']))
        if os.path.exists(class_csv):
            with open(class_csv, 'r', encoding='utf-8') as f:
                class_result = json.load(f)
                question_type = class_result['class']  # 提取分类标签

            if question_type == 'E':  # 仅对分类结果为 E 的问题生成 SQL
                logger.opt(colors=True).info('<blue>Start process question {} {}</>'.format(question['id'], question['question'].replace('<', '')))
                # 模型输出问题的sql语句
                sql = model.nl2sql(question['question'])
                logger.info(sql.replace('<>', ''))
        # 将sql语句写入文件
        with open(sql_csv, 'w', encoding='utf-8') as f:
            save_result = copy.deepcopy(question)
            save_result['sql'] = sql
            json.dump(save_result, f, ensure_ascii=False)

'''

'''
def generate_answer(model):
    workflow = FinancialAnnualReportWorkflow(model)
    answer_dir = os.path.join(cfg.DATA_PATH, 'answers')
    if not os.path.exists(answer_dir):
        os.mkdir(answer_dir)
    for question in workflow.test_questions:
        answer_csv = os.path.join(answer_dir, '{}.csv'.format(question['id']))
        result = copy.deepcopy(question)
        answer = workflow.answer_question(question)
        result['answer'] = answer if answer is not None else ''
        with open(answer_csv, 'w', encoding='utf-8') as f:
            try:
                json.dump(result, f, ensure_ascii=False)
            except:
                result['answer'] = ''
                json.dump(result, f, ensure_ascii=False)

'''
该函数主要用于：加载测试问题集 检查预生成答案缓存 执行答案后处理（如脱敏）
'''
def make_answer():
    answers = [] # 初始化答案存储列表
    # 加载测试问题集（假设返回结构：[{'id':1, 'question':'...'}, ...]）
    test_questions = load_test_questions()
    # 构建答案存储目录路径（如：./data/answers）
    answer_dir = os.path.join(cfg.DATA_PATH, 'answers')
    # 遍历每个测试问题
    for question in test_questions:
        # 构造答案文件路径（如：./data/answers/1.csv）
        answer_csv = os.path.join(answer_dir, '{}.csv'.format(question['id']))

        # 检查是否已有缓存答案
        if os.path.exists(answer_csv):
            # 读取已存在的答案文件
            with open(answer_csv, 'r', encoding='utf-8') as f:
                answer = json.load(f)
                question = answer
        else: # 无缓存则初始化空答案
            question['answer'] = ''
        # 答案重写处理（如去除敏感信息）
        question['answer'] = re_util.rewrite_answer(question['answer'])
        # 收集处理后的答案
        answers.append(question)
    # 构建输出路径（如：./data/result_20231025.json）
    save_path = os.path.join(cfg.DATA_PATH, 'result_{}.json'.format(datetime.now().strftime('%Y%m%d')))
    # 写入最终结果文件
    with open(save_path, 'w', encoding='utf-8') as f:
        for answer in answers:
            try:
                line = json.dumps(answer, ensure_ascii=False).encode('utf-8').decode() + '\n'
            except:
                answer['answer'] = ''
                line = json.dumps(answer, ensure_ascii=False).encode('utf-8').decode() + '\n'
            f.write(line)
