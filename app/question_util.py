import re
from loguru import logger

from . import prompt_util


def normalize_company_name(text):
    text = str(text or "")
    text = re.sub(r'[\(\)（）\s]', '', text)
    text = re.sub(r'(集团股份有限公司|股份有限公司|有限责任公司|集团有限公司|集团公司|有限公司)$', '', text)
    return text

'''
从问题中通过正则表达式匹配可能的年份
'''
def get_years_of_question(question):
    # 使用正则表达式 \d{4} 从问题文本中提取所有 4 位数字（即年份）。
    years = re.findall('\d{4}', question)

    # 如果问题中只找到一个明确的年份，尝试推断相关年份
    if len(years) == 1:
        # 匹配如"上年"、"前一年"、"1年前"等表达
        if re.search('(([上前去]的?[1一]|[上去])年|[1一]年(前|之前))', question) and '上上年' not in question:
            # 计算并添加前一年（如2020 → 添加2019）
            last_year = int(years[0]) - 1
            years.append(str(last_year))
        # 匹配如"前年"、"上上年"、"两年前"等表达
        if re.search('((前|上上)年|[2两]年(前|之前))', question):
            # 计算并添加前两年（如2020 → 添加2018）
            last_last_year = int(years[0]) - 2
            years.append(str(last_last_year))
        # 匹配如"前两年"、"上两年"等表达
        if re.search('[上前去]的?[两2]年', question):
            # 同时添加前一年和前两年
            last_year = int(years[0]) - 1
            last_last_year = int(years[0]) - 2
            years.append(str(last_year))
            years.append(str(last_last_year))
        # 匹配如"下一年"、"1年后"等表达
        if re.search('([后下]的?[1一]年|[1一]年(后|之后|过后))', question):
            next_year = int(years[0]) + 1
            years.append(str(next_year))
        # 匹配如"两年后"等表达
        if re.search('[2两]年(后|之后|过后)', question):
            next_next_year = int(years[0]) + 2
            years.append(str(next_next_year))
        # 匹配如"后两年"、"接下来两年"等表达
        if re.search('(后|接下来|下)的?[两2]年', question):
            next_year = int(years[0]) + 1
            next_next_year = years[0] + 2
            years.append(str(next_year))
            years.append(str(next_next_year))
    # 当找到两个年份时
    if len(years) == 2:
        # 匹配如"2010-2020"、"2010年至2020年"等表达
        if re.search('\d{4}年?[到\-至]\d{4}年?', question):
            year0 = int(years[0])
            year1 = int(years[1])
            # 提取两个年份之间的所有年份（如2010和2020 → 添加2011-2019）
            for year in range(min(year0, year1) + 1, max(year0, year1)):
                years.append(str(year))

    return years

'''
匹配问题中涉及到的公司名称
'''
def get_match_company_names(question, pdf_info):
    question = re.sub('[\(\)（）]', '', question) # 删除问题中的中文/英文括号
    normalized_question = normalize_company_name(question)

    matched_companys = []  # 存储匹配到的公司名称列表
    for k, v in pdf_info.items():   # 遍历每个公司条目
        company = v['company']
        abbr = v['abbr']   # 公司缩写
        if company in question:   # 检查公司全称是否在问题中
            matched_companys.append(company)
        if abbr in question:
            matched_companys.append(abbr)
        if normalize_company_name(company) in normalized_question:
            matched_companys.append(company)
        if normalize_company_name(abbr) in normalized_question:
            matched_companys.append(abbr)
    return matched_companys  

'''
用于根据问题和PDF信息匹配最相关的PDF文件名，主要基于公司名称/缩写和年份的匹配
'''
def get_match_pdf_names(question, pdf_info):
    # 内部辅助函数，用于计算两个字符串的共同字符
    def get_matching_substrs(a, b):
        return ''.join(set(a).intersection(b))
    # 从问题中提取所有相关年份
    years = get_years_of_question(question)
    normalized_question = normalize_company_name(question)
    match_keys = []  # 初始化空列表match_keys用于存储匹配的PDF键名
    # 遍历PDF信息字典pdf_info的每一项
    for k, v in pdf_info.items():
        # 提取公司全名(company)、缩写(abbr)和年份(year)，并清理年份字符串
        company = v['company']
        abbr = v['abbr']
        year = v['year'].replace('年', '').replace(' ', '')
        if company in question and year in years:# 公司全名出现在问题中且年份匹配
            match_keys.append(k)
        if abbr in question and year in years:  # 公司缩写出现在问题中且年份匹配
            match_keys.append(k)
        if year in years:
            if normalize_company_name(company) in normalized_question:
                match_keys.append(k)
            if normalize_company_name(abbr) in normalized_question:
                match_keys.append(k)
    match_keys = list(set(match_keys))  # 对匹配结果进行去重（因为可能通过全名和缩写都匹配了同一个PDF）
    # 前面已经完全匹配了年份, 所以可以删除年份
    # 计算每个匹配键名与问题（去除年份后）的重叠字符长度
    overlap_len = [len(get_matching_substrs(x, re.sub('\d?', '', question))) for x in match_keys]
    # 将匹配键名与重叠度配对，并按重叠度降序排序  这样最相关的PDF会排在前面
    match_keys = sorted(zip(match_keys, overlap_len), key=lambda x: x[1], reverse=True)
    # print(match_keys)
    if len(match_keys) > 1:
        # logger.info(question)
        # 多个结果重合率完全相同
        if len(set([t[1] for t in match_keys])) == 1:
            pass   # 多个结果重合率完全相同，不做处理
        else:
            logger.warning('匹配到多个结果{}'.format(match_keys))
            match_keys = match_keys[:1]  # 只保留重叠度最高的一个
        # for k in match_keys:
        #     print(k[0])
    match_keys = [k[0] for k in match_keys]  # 从配对结果中提取PDF键名（去掉重叠度信息）
    return match_keys  # 返回最终匹配的PDF键名列表

'''
根据给定的PDF键名列表，从PDF信息字典中提取对应的公司名称、公司缩写和公司代码
'''
def get_company_name_and_abbr_code_of_question(pdf_keys, pdf_info):
    company_names = []
    for pdf_key in pdf_keys:
        company_names.append((pdf_info[pdf_key]['company'], pdf_info[pdf_key]['abbr'], pdf_info[pdf_key]['code']))
    return company_names


def parse_keyword_from_answer(anoy_question, answer):
    key_words = set()
    key_word_list = answer.split('\n')
    for key_word in key_word_list:
        key_word = key_word.replace(' ', '')
        # key_word = re.sub('年报|报告|是否', '', key_word)
        if (key_word.endswith('公司') and not key_word.endswith('股公司')) or re.search(
                r'(年报|财务报告|是否|最高|最低|相同|一样|相等|在的?时候|财务数据|详细数据|单位为|年$)', key_word):
            continue
        if key_word.startswith('关键词'):
            key_word = re.sub("关键词[1-9][:|：]", "", key_word)
            if key_word in ['金额', '单位','数据']:
                continue
            if  key_word in anoy_question and len(key_word) > 1:
                key_words.add(key_word)
    return list(key_words)


def anoy_question_xx(question, real_company, years):
    question_new = question
    question_new = question_new.replace(real_company, 'XX公司')
    for year in years:
        question_new = question_new.replace(year, 'XXXX')

    return question_new

'''
该函数用于从用户提问中提取核心关键词
'''
def parse_question_keywords(model, question, real_company, years):
    question = re.sub('[\(\)（）]', '', question).replace('为？','是什么？').replace('是？','是什么？').replace('为多少','是多少') # 删除所有括号  # 统一问题句式
    # 假设的匿名函数
    anoy_question = anoy_question_xx(question, real_company, years)
    anoy_question = re.sub(r'(XX公司|XXXX年|XXXX|保留两位小数|对比|相比|报告期内|哪家|上市公司|第[1234567890一二三四五六七八九十]+[高低]|最[高低](的|的前|的后)?[1234567890一二三四五六七八九十]+家)', '', anoy_question)
    if anoy_question[0] == '的':
        anoy_question = anoy_question[1:]
    answer = model(prompt_util.prompt_get_key_word.format(anoy_question))

    key_words = parse_keyword_from_answer(anoy_question, answer)
    # 无法提取，删除的再试一次
    if len(key_words) == 0:
        anoy_question = anoy_question.replace('的', '')
        answer = model(prompt_util.prompt_get_key_word.format(anoy_question))
        key_words = parse_keyword_from_answer(anoy_question, answer)
    if len(key_words) == 0:
        logger.warning('无法提取关键词')
        key_words = [anoy_question]

    return anoy_question, key_words
