
import re
from loguru import logger
#金额单位：元，金额与元之间无空格。
# 比值、比率问题不需百分号；速动比率、流动比率也不需转化为百分比；其他情况需要。

def get_formulas():
    formulas = [
        '研发经费与利润=研发费用/净利润',
        '研发经费与营业收入=研发费用/营业收入',
        '研发人员占职工=研发人员的数量/在职员工的数量合计',
        '研发人员占总职工=研发人员的数量/在职员工的数量合计',
        '研发人员在职工=研发人员的数量/在职员工的数量合计',
        '研发人员所占=研发人员的数量/在职员工的数量合计',
        '流动比率=流动资产合计/流动负债合计',
        '速动比率=(流动资产合计-存货)/流动负债合计',
        '硕士及以上人员占职工=(硕士研究生+博士)/在职员工的数量合计',
        '硕士及以上学历的员工占职工=(硕士研究生+博士)/在职员工的数量合计',
        '硕士及以上学历人员占职工=(硕士研究生+博士)/在职员工的数量合计',
        '研发经费占费用=研发费用/(销售费用+财务费用+管理费用+研发费用)',
        '研发经费在总费用=研发费用/(销售费用+财务费用+管理费用+研发费用)',
        '研发经费占总费用=研发费用/(销售费用+财务费用+管理费用+研发费用)',
        '营业利润率=营业利润/营业收入',
        '资产负债比率=负债合计/资产总计',
        '现金比率=货币资金/流动负债合计',
        '非流动负债比率=非流动负债合计/负债合计',
        '流动负债比率=流动负债合计/负债合计',
        '流动负债的比率=流动负债合计/负债合计',
        '净资产收益率=净利润/净资产',
        '净利润率=净利润/营业收入',
        '营业成本率=营业成本/营业收入',
        '管理费用率=管理费用/营业收入',
        '财务费用率=财务费用/营业收入',
        '毛利率=(营业收入-营业成本)/营业收入',
        '三费比重=(销售费用+管理费用+财务费用)/营业收入',
        '三费（销售费用、管理费用和财务费用）占比=(销售费用+管理费用+财务费用)/营业收入',
        '投资收益占营业收入=投资收益/营业收入',
    ]
    formulas = [t.split('=') for t in formulas]
    return formulas


def growth_formula():
    formulas = ['销售费用增长率=(销售费用-上年销售费用)/上年销售费用',
        '财务费用增长率=(财务费用-上年财务费用)/上年财务费用',
        '管理费用增长率=(管理费用-上年管理费用)/上年管理费用',
        '研发费用增长率=(研发费用-上年研发费用)/上年研发费用',
        '负债合计增长率=(负债合计-上年负债合计)上年负债合计',
        '总负债增长率=(总负债-上年总负债)/上年总负债',
        '流动负债增长率=(流动负债-上年流动负债)/上年流动负债',
        '货币资金增长率=(货币资金-上年货币资金)/上年货币资金',
        '固定资产增长率=(固定资产-上年固定资产)/上年固定资产',
        '无形资产增长率=(无形资产-上年无形资产)/上年无形资产',
        '资产总计增长率=(资产总计-上年资产总计)/上年资产总计',
        '投资收益增长率=(投资收益-上年投资收益)/上年投资收益',
        '总资产增长率=(资产总额-上年资产总额)/上年资产总额',
        '营业收入增长率=(营业收入-上年营业收入]/上年营业收入',
        '营业利润增长率=(营业利润-上年营业利润)/上年营业利润',
        '净利润增长率=(净利润-上年净利润)/上年净利润',
        '现金及现金等价物增长率=(现金及现金等价物-上年现金及现金等价物)/上年现金及现金等价物']
    formulas = [t.split('=') for t in formulas]
    return formulas

'''
判断问题是否属于要计算增长率的问题
'''
def is_type2_growth_rate(question):
    # 问题不包含年份
    if len(re.findall('\d{4}', question)) == 0:
        return False
    if '增长率' in question:
        return True
    return False


def is_type2_formula(question):
    # 检查问题文本中是否包含四位数字（表示年份）
    if len(re.findall('\d{4}', question)) == 0:
        return False    
    # 调用函数获取公式列表。
    formulas = get_formulas()
    # 遍历公式列表中的每个公式
    for k, v in formulas:
        # 检查问题文本中是否包含当前公式的名称。
        if k in question:
            return True
    return False

'''
用于从公式字符串中提取关键词
'''
def get_keywords_of_formula(value):
    keywords = re.split('[(+-/)]', value)
    keywords = [t for t in keywords if len(t) > 0]
    return keywords

'''
用于根据输入问题生成分步问题及相关参数
question：原始问题文本。
keywords：问题关键词。
real_comp：公司名称。
year：年份。


典型输出示例
输入的问题可能是 2022年腾讯科技的毛利率是多少？
输出：
step_questions = [
    "2022年腾讯科技的毛利润是多少元?",
    "2022年腾讯科技的营业收入是多少元?"
]
question_keywords = ["毛利润", "营业收入"]
variable_names = ["毛利润", "营业收入"]
step_years = ["2022","2022"]
formula = "毛利润/营业收入"
question = "根据公式，毛利率=毛利润/营业收入、"
'''
def get_step_questions(question, keywords, real_comp, year):
    new_question = question
    # 存储分步问题、关键词、变量名称、年份、公式
    step_questions = []
    question_keywords = []
    variable_names = []
    step_years = []
    formula = None
    question_formula = None

    # 判断问题是否包含“增长率”关键词。
    if '增长率' in question:
        # 如果关键词是“增长率”，则使用问题文本作为关键词，并生成分步关键词列表
        if keywords == '增长率':
            keywords = new_question
        
        # 构造元数据
        question_keywords = [keywords.replace('增长率', '')] * 2 + [keywords]
        variable_names = ['A', 'B', 'C']  # 当前年值/上年值/增长率
        formula = '(A-B)/B' # 基础增长率公式
        question_formula = '根据公式，=(-上年)/上年'  # 默认公式描述
        # 遍历增长率公式列表。
        for formula_key, formula_value in growth_formula():
            # 如果增长率的公式名在问题中。
            if formula_key in new_question.replace('的', ''):  # 过滤干扰词
                # 创建问题增长率的计算公式
                question_formula = '根据公式，{}={},'.format(formula_key, formula_value)
        # 生成分步问题
        step_years = [year, str(int(year)-1), year]
        step_questions.append(new_question.replace('增长率', '')) # 先计算当前年值
        step_questions.append(new_question.replace('增长率', '').replace(year, str(int(year)-1))) # 再计算上年值
        step_questions.append(new_question)
    # 处理普通公式问题
    else:
        # 获取预定义公式库
        formulas = get_formulas()
        # 遍历公式
        for k, v in formulas: 
            # 匹配公式名称 
            if k in new_question:
                # 从匹配到的公式中提取变量名
                variable_names = get_keywords_of_formula(v)
                formula = v
                # 根据得到的变量名去构建分步问题
                for name in variable_names:
                    if '人数' in question or '数量' in question or '人员' in question:
                        step_questions.append('{}年{}{}有多少人?如果已知信息没有提供, 你应该回答为0人。'.format(year, real_comp, name))
                    else:
                        step_questions.append('{}年{}的{}是多少元?'.format(year, real_comp, name))
                    # 添加分布步骤的关键词。
                    question_keywords.append(name)
                    # 添加分布步骤的年份
                    step_years.append(year)
                # 记录公式
                question_formula = '根据公式，{}={}'.format(k, v)
                break  # 匹配到第一个符合的公式就跳出
    return step_questions, question_keywords, variable_names, step_years, formula, question_formula


def get_question_formula_prompt(question):
    prompt = None
    if '增长率' in question:
        prompt = '问题"{}"中的计算公式是什么?请按照"(XXXX-上年度的XXXX)/上年度的XXXX"的格式写出, 你只需给出公式,不要回答其他内容.'.format(question)
    else:
        formulas = get_formulas()
        for k, v in formulas:
            if k in question:
                prompt = '问题"{}"中的计算公式是什么? 你只需给出公式,不要回答其他内容.'.format(question)
                break
    return prompt

# 从自然语言文本中提取有效数值
def get_variable_value_from_answer(answer):
    # 正则提取所有数字字符组合
    numbers = re.findall(r'[+\-\d\.]*', answer)
    # 过滤常见年份
    numbers = [t for t in numbers if t not in ['2018', '2019', '2020', '2021', '2022']]
    # 按字符串长度降序排序
    numbers = sorted(numbers, key=lambda x: len(x), reverse=True)
    # 返回最长数值
    if len(numbers) >= 1:
        return numbers[0]
    else:
        return None


def get_question_formula(question):
    formulas = get_formulas()
    formula = None
    for k, v in formulas:
        if k in question:
            formula = '{}={}'.format(k, v)
    return formula


if __name__ == '__main__':
    print(get_keywords_of_formula('(净利润-上年净利润)/上年净利润'))
