import os  # 用于与操作系统进行交互
import json # 导入 json 模块，用于处理 JSON 格式的数据
import re  # 用于处理正则表达式，进行字符串匹配、搜索、替换等操作
import pandas as pd  # 处理结构化数据x 
from loguru import logger  # 日志记录库
from functools import cmp_to_key
from config import cfg  # 导入配置文件
from . import re_util  # 自定义正则表达式相关的工具函数


'''
从txt中读取所有pdf文件名，并将文件名提取为统一的json格式保存
'''
def download_data():
    # 打开文本文件,读取所有PDF文件名列表
    with open(cfg.DATA_PATH + 'test/C-list-pdf-name.txt', 'r', encoding='utf-8') as f:
        pdf_names = [line.strip('\n') for line in f.readlines()]
        print(pdf_names[:10])  # 打印前十个PDF的文件名
    ds = {}  # 创建空字典存储PDF元数据
    for name in pdf_names:
        # 路径拼接
        pdf_path = os.path.join(cfg.DATA_PATH + 'allpdf', name)
        split = name.split('__') # 按双下划线分割文件名,提取文件名属性
        ds[name] = {
            'key': name,
            'pdf_path': pdf_path,
            'company': split[1],
            'code': split[2],
            'abbr': split[3],
            'year': split[4]
        }
    
    # 保存为json文件
    with open(os.path.join(cfg.DATA_PATH, 'pdf_info.json'), 'w', encoding='utf-8') as f:
        json.dump(ds, f, ensure_ascii=False, indent=4)

'''
加载测试问题
'''
def load_test_questions():
    path = os.path.join(cfg.DATA_PATH, 'test/C-list-question.json')
    with open(path, 'r', encoding='utf-8') as f:
        test_questions = [json.loads(line) for line in f.readlines()]
    test_questions = test_questions
    return test_questions


'''
读取所有pdf_info信息到字典中。
file_name： company,year,....
'''
def load_pdf_info():
    with open(os.path.join(cfg.DATA_PATH, 'pdf_info.json'), 'r', encoding='utf-8') as f:
        pdf_info = json.load(f)
    part = {}
    for k, v in list(pdf_info.items()):
        part[k] = v
    return part


'''
获取原pdf路径
'''
def get_raw_pdf_path(key):
    pdf_info = load_pdf_info()
    return pdf_info[key]['pdf_path']


'''
集中加载多个JSON格式的数据表，返回统一结构字典   
'''
def load_total_tables():
    key_and_paths = [
        ('basic_info', os.path.join(cfg.DATA_PATH, 'basic_info.json')),
        ('employee_info', os.path.join(cfg.DATA_PATH, 'employee_info.json')),
        ('cbs_info', os.path.join(cfg.DATA_PATH, 'cbs_info.json')),
        ('cscf_info', os.path.join(cfg.DATA_PATH, 'cscf_info.json')),
        ('cis_info', os.path.join(cfg.DATA_PATH, 'cis_info.json')),
        ('dev_info', os.path.join(cfg.DATA_PATH, 'dev_info.json')),
    ]
    tables = {}
    for key, path in key_and_paths:
        with open(path, 'r', encoding='utf-8') as f:
            tables[key] = json.load(f)
    return tables

# 返回pdf表格信息路径
def get_pdf_table_path(key):
    path = {
        'basic_info': os.path.join(cfg.DATA_PATH, 'pdf_docs', key, 'basic_info.txt'),
        'employee_info': os.path.join(cfg.DATA_PATH, 'pdf_docs', key, 'employee_info.txt'),
        'cbs_info': os.path.join(cfg.DATA_PATH, 'pdf_docs', key, 'cbs_info.txt'),
        'cscf_info': os.path.join(cfg.DATA_PATH, 'pdf_docs', key, 'cscf_info.txt'),
        'cis_info': os.path.join(cfg.DATA_PATH, 'pdf_docs', key, 'cis_info.txt'),
        'dev_info': os.path.join(cfg.DATA_PATH, 'pdf_docs', key, 'dev_info.txt'),
    }
    return path

'''
检查要加载的key是否在all_tables中。
如果在就提取目标表格数据，如果不在就日志记录
'''
def load_pdf_tables(key, all_tables):
    tables = {}
    for k, v in all_tables.items():
        if key in v.keys() and k in v[key]:  # 检查是否在已解析出的表中。
            lines = v[key][k]  # 提取目标表格数据
            lines = [re_util.sep_numbers(line) for line in lines]  # 对每行进行数字分隔
            tables[k] = lines
        else:
            logger.warning('{} not in {}'.format(key, k))
            tables[k] = []
    return tables

'''
清洗并转换基础信息表格数据为结构化元组
'''
def basic_info_to_tuple(year, table_lines):
    tuples = []  # 存储最终的结构化数据
    # 遍历每一行表格内容
    for line in table_lines:
        if 'page' in line:
            continue
        # 清洗行数据
        line = line.strip('\n').split('|')   # 示例输入行： "公司名称 | 腾讯科技 | 成立日期 | 1998年"
        # 构建清洗后的字段列表
        line_text = []
        for sp in line:
            if sp == '':
                continue
            sp = sp.replace(' ', '').replace('"', '')
            if len(line_text) >= 1 and line_text[-1] == sp:
                continue
            line_text.append(sp)
        # 提取并规范化字段名 
        if len(line_text) >= 1:
            row_name = line_text[0]
            row_name = re.sub('[(（].*[）)]', '', row_name)
            row_name = re.sub('(公司|的)', '', row_name)
            # row_name = '"{}"'.format(row_name)
        if len(line_text) == 1:
            tuples.append(('basic_info', year, row_name, ''))
        elif len(line_text) == 2:
            tuples.append(('basic_info', year, row_name, line_text[1]))
        elif len(line_text) == 3:
            tuples.append(('basic_info', year, row_name, '|'.join(line_text[1:])))
        elif len(line_text) >= 4:
            tuples.append(('basic_info', year, row_name, line_text[1]))
            tuples.append(('basic_info', year, line_text[2], line_text[3]))
    return tuples  # 返回结构化表格内容


def employee_info_to_tuple(year, table_lines):
    tuples = []
    for line in table_lines:
        if 'page' in line:
            continue
        line = line.strip('\n').split('|')
        line_text = []
        for sp in line:
            if sp == '':
                continue
            sp = re.sub('[ ,]', '', sp)
            sp = re.sub('[(（]人[）)]', '', sp)
            if len(line_text) >= 1 and line_text[-1] == sp:
                continue
            line_text.append(sp)
        if len(line_text) >= 2:
            try:
                number = float(line_text[1])
                row_name = line_text[0]
                tuples.append(('employee_info', year, row_name, line_text[1]+'人'))
            except:
                continue
    return tuples


def dev_info_to_tuple(year, table_lines):
    tuples = []
    for line in table_lines:
        if 'page' in line:
            continue
        if not '研发人员' in line:
            continue
        line = line.strip('\n').split('|')
        line_text = []
        for sp in line:
            if sp == '':
                continue
            sp = re.sub('[ ,]', '', sp)
            sp = re.sub('[(（]人[）)]', '', sp)
            if len(line_text) >= 1 and line_text[-1] == sp:
                continue
            line_text.append(sp)
        if len(line_text) >= 2:
            tuples.append(('dev_info', year, line_text[0], line_text[1]+'人'))
    return tuples


def get_unit(pdf_key, table):
    unit = 1
    if len(table) == 0:
        return unit
    page_num = table[0].strip().split('|')[1]
    pages = load_pdf_pure_text(pdf_key, warn_if_missing=False)
    for idx, page_item in enumerate(pages):
        if str(page_item['page']) == page_num:
            last_page_lines = []
            if idx > 0:
                last_page_lines = pages[idx-1]['text'].split('\n')[-10:]
            current_page_lines = page_item['text'].split('\n')
            search_string = None
            for line in last_page_lines + current_page_lines:
                re_unit = re.findall('单位\s*[:：；].{0,3}元', line) + \
                    re.findall('人民币.{0,3}元', line)
                if len(re_unit) != 0:
                    search_string = re_unit[0]
                    break
            if search_string is not None:
                if '百万' in search_string:
                    unit = 1000000
                elif '万' in search_string:
                    unit = 10000
                elif '千' in search_string:
                    unit = 1000
                else:
                    pass
            else:
                print('cannot find unit for key {} page {}'.format(pdf_key, page_num))
                print(page_item['text'])

            if unit != 1:
                print(pdf_key)
                print(search_string)
                print(page_item['text'])
            break
    if unit != 1:
        logger.info('{}的单位是{}'.format(pdf_key, unit))
    return unit


def fs_info_to_tuple(pdf_key, table_name, year, table_lines):
    unit = get_unit(pdf_key, table_lines)
    # print('table name and unit ', table_name, unit)
    tuples = []
    page_id = None
    for line in table_lines:
        if 'page' in line:
            page_id = line.split('page')[1]
            continue
        line = line.strip('\n').split('|')
        line_text = []
        for sp in line:
            if sp == '':
                continue
            sp = re.sub('[ ,]', '', sp)
            if len(line_text) >= 1 and line_text[-1] == sp:
                continue
            line_text.append(sp)
        if len(line_text) == 1:
            continue
        if len(line_text) >= 2:
            row_name = line_text[0]
            row_name = re.sub('[\d \n\.．]', '', line[0])
            row_name = re.sub('（[一二三四五六七八九十]）', '', row_name)
            row_name = re.sub('\([一二三四五六七八九十]\)', '', row_name)
            row_name = re.sub('[一二三四五六七八九十][、.]', '', row_name)
            row_name = re.sub('其中：', '', row_name)
            row_name = re.sub('[加减]：', '', row_name)
            row_name = re.sub('（.*）', '', row_name)
            row_name = re.sub('\(.*\)', '', row_name)

            if row_name == '':
                continue

            row_values = []
            for value in line_text[1:]:
                if value == '' or value == '-':
                    continue
                if set(value).issubset(set('0123456789.,-')):
                    try:
                        if re_util.is_valid_number(value):
                            row_values.append('{:.2f}元'.format(float(value)*unit))
                    except:
                        logger.error('Invalid value {} {} {}'.format(value, pdf_key, table_name))
                        row_values.append(value + '元')
            # print(line_text)
            # print(row_values, '----')
            if len(row_values) == 1:
                # logger.warning('Invalid line(2 values) {} in {} {}'.format(line_text, table_name, year))
                tuples.append((table_name, year, row_name, row_values[0]))
            elif len(row_values) == 2:
                tuples.append((table_name, year, row_name, row_values[0]))
                tuples.append((table_name, str(int(year)-1), row_name, row_values[1]))
            elif len(row_values) >= 3:
                tuples.append((table_name, year, row_name, row_values[1]))
                tuples.append((table_name, str(int(year)-1), row_name, row_values[2]))
    return tuples

# 根据表格类型分发处理逻辑
def table_to_tuples(pdf_key, year, table_name, table_lines):
    if table_name == 'basic_info':
        return basic_info_to_tuple(year, table_lines)
    elif table_name == 'employee_info':
        return employee_info_to_tuple(year, table_lines)
    elif table_name == 'dev_info':
        return dev_info_to_tuple(year, table_lines)
    else:
        return fs_info_to_tuple(pdf_key, table_name, year, table_lines)

'''
根据公司和年份加载对应的PDF表格数据，并进行字段别名标准化，返回结构化元组
'''
def load_tables_of_years(company, years, pdf_tables, pdf_info):
    table = []
    for year in years:
        year = year.replace('年', '')
        pdf_key = None
        for k, v in pdf_info.items():
            if v['company'] == company and year in v['year']:
                pdf_key = k
        if pdf_key is None:
            logger.error('Cannot find pdf key for {} {}'.format(company, year))
            continue
        # 加载特定PDF的表格数据
        year_tables = load_pdf_tables(pdf_key, pdf_tables)
        for table_name, table_lines in year_tables.items():
            # 返回结构化表格元组，并将元组加入到列表table中。
            table.extend(table_to_tuples(pdf_key, year, table_name, table_lines))
    
    # table可能是这样的:
#     [
#     (公司, 年份, "营业收入", 数值1),
#     (公司, 年份, "净利润", 数值2),
#     ...
#       ]

    alias = {
        '在职员工的数量合计': '职工总人数',
        '负债合计': '总负债',
        '资产总计': '总资产',
        '流动负债合计': '流动负债',
        '非流动负债合计': '非流动负债',
        '流动资产合计': '流动资产',
        '非流动资产合计': '非流动资产'
    }
    new_table = []
    for row in table:
        table_name, row_year, row_name, row_value = row
        new_table.append((table_name, row_year, row_name, row_value))
        if row_name in alias:
            new_table.append((table_name, row_year, alias[row_name], row_value))
    
    return new_table

'''
用于将表格行数据转换为 Pandas DataFrame
'''
def table_to_dataframe(table_rows):
    # 将 table_rows 转换为 DataFrame，并指定列名
    df = pd.DataFrame(table_rows, columns=['table_name', 'row_year', 'row_name', 'row_value'])
    # 将 row_year 列的数据转换为数值类型。
    df['row_year'] = pd.to_numeric(df['row_year'])
    # 删除 DataFrame 中的重复行
    df.drop_duplicates(inplace=True)
    # 按 row_name 和 row_year 列对 DataFrame 进行排序
    df.sort_values(by=['row_name', 'row_year'], inplace=True)
    return df

'''
用于在表格中添加增长率列
'''
def add_growth_rate_in_table(table_rows):
    # 将 table_rows 转换为 Pandas DataFrame
    df = table_to_dataframe(table_rows)
    # 初始化一个空列表 added_rows，用于存储新增的增长率行
    added_rows = []
    # 遍历 DataFrame 的每一行
    for idx, (index, row) in enumerate(df.iterrows()):
        # 获取前一行的数据
        last_row = df.iloc[idx-1]
        # 检查前一行的行名是否与当前行相同，且前一行的年份是否比当前行少一年。
        if last_row['row_name'] == row['row_name'] and last_row['row_year'] == row['row_year'] -1:
            # 从 row_value 中提取数值。
            last_values = re_util.find_numbers(last_row['row_value'])
            current_values = re_util.find_numbers(row['row_value'])
            # 检查前一行和当前行的数值是否有效
            if len(last_values) > 0 and len(current_values) > 0:
                # 确保前一行的数值不为零，避免除零错误。
                if last_values[0] != 0:
                    # 计算增长率并添加到 added_rows 列表中
                    growth_rate = (current_values[0]-last_values[0])/last_values[0] * 100
                    added_rows.append([row['table_name'], str(row['row_year']), row['row_name'] + '增长率', '{:.2f}%'.format(growth_rate)])
    # 将原始表格行和新增的增长率行合并
    merged_rows = table_rows + added_rows
    return merged_rows

'''
对表格行数据（table_rows）进行跨年份的数值或文本对比，
生成新的对比行（如“A年与B年相比，指标X的值相同/不同”），并将这些新行追加到原始数据中
'''
def add_text_compare_in_table(table_rows):
    df = table_to_dataframe(table_rows)
    added_rows = []
    for idx, (index, row) in enumerate(df.iterrows()):
        if idx == 0:
            continue

        last_row = df.iloc[idx-1]
        if last_row['row_name'] == row['row_name']:
            last_values = re_util.find_numbers(last_row['row_value'])
            current_values = re_util.find_numbers(row['row_value'])
            if len(last_values) == 0 and len(current_values) == 0:
                if row['row_value'] != last_row['row_value']:
                    row_value = '不相同且不同'
                else:
                    row_value = '相同'
                added_rows.append([row['table_name'], '{}与{}相比'.format(row['row_year'], last_row['row_year']),
                    row['row_name'], row_value])
    merged_rows = table_rows + added_rows
    return merged_rows

'''
用于将表格行数据转换为自然语言文本描述
    ('basic_info', '2020', '公司名称', 'ABC公司'),
    ('employee_info', '2020', '员工人数', '500'),
    ('financial_info', '2020', '营业收入', '1亿元')

    "2020年的"公司名称"是"ABC公司",2020年的"员工人数"有500,2020年的"营业收入"是1亿元,
'''
def table_to_text(company, question, table_rows, with_year=True):
    text_lines = []
    for row in table_rows:
        table_name, row_year, row_name, row_value = row
        
        if table_name == 'basic_info':
            row_value = '"{}"'.format(row_value)
        else:
            row_name = '"{}"'.format(row_name)

        if not with_year:
            row_year = ''
        else:
            row_year += '年的'
        if row_value in ['相同', '不相同且不同']:
            # print(row_year, row_name, row_value)
            line = '{}的{}{},'.format(row_year, row_name, row_value)
        else:
            if table_name == 'employee_info':
                line = '{}{}有{},'.format(row_year, row_name, row_value)
            else:
                line = '{}{}是{},'.format(row_year, row_name, row_value)
        if line not in text_lines:
            text_lines.append(line)
    return ''.join(text_lines)


def load_pdf_text(key):
    text = []
    text_path = os.path.join(cfg.DATA_PATH, 'pdf_docs', key, 'docs.txt')
    if not os.path.exists(text_path):
        logger.warning('{} not exists'.format(text_path))
        return text
    with open(text_path, 'r', encoding='utf-8') as f:
        text_lines = [json.loads(line) for line in f.readlines()]
    text = [line for line in text_lines if \
            'inside' in line and \
            'allrow' in line and \
            line['type'] in ['text', 'excel'] and \
            line['inside'].strip(' ') != '']
    return text


def page_to_text(page: list):
    text = ''
    line_index = 0
    while line_index < len(page):
        if page[line_index]['type'] == 'text':
            text += page[line_index]['inside'] + '\n'
            line_index += 1
        elif page[line_index]['type'] == 'excel':
            table = []
            while line_index < len(page) and page[line_index]['type'] == 'excel':
                table.append(page[line_index])
                line_index += 1
            table_text = table_to_text(table)
            text += table_text + '\n'
    return text

'''
按照页数加载纯文本内容, 返回列表
'''

def load_pdf_pure_text(key, warn_if_missing=True):
    text_lines = []
    text_path = os.path.join(cfg.DATA_PATH, 'pdf_docs', key, 'pure_content.txt')
    if not os.path.exists(text_path):
        if warn_if_missing:
            logger.warning('{} not exists'.format(text_path))
        return text_lines
    with open(text_path, 'r', encoding='utf-8', errors='ignore') as f:
        try:
            lines = f.readlines()
            text_lines = [json.loads(line) for line in lines]
            text_lines = sorted(text_lines, key=lambda x: x['page'])
            if len(text_lines) == 0:
                logger.warning('{} is empty'.format(text_path))
        except Exception as e:
            logger.error('Unable to load {}, {}'.format(text_path, e))
    return text_lines


def load_pdf_pure_text_alltxt(key):
    text_lines = []
    text_path = os.path.join(cfg.DATA_PATH, 'alltxt', '{}.txt'.format(os.path.splitext(key)[0]))
    # print(text_path)
    if not os.path.exists(text_path):
        logger.warning('{} not exists'.format(text_path))
        return text_lines
    with open(text_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        raw_lines = [json.loads(line) for line in lines]
        for line in raw_lines:
            if 'type' not in line or 'inside' not in line:
                continue
            if len(line['inside'].replace(' ', '')) ==  0:
                continue
            if line['type'] in ['页脚', '页眉']:
                continue
            if line['type'] == 'text':
                text_lines.append(line)
            elif line['type'] == 'excel':
                try:
                    row = eval(line['inside'])
                    line['inside'] = '\t'.join(row)
                    text_lines.append(line)
                except:
                    logger.warning('Invalid line {}'.format(line))
            else:
                logger.warning('Invalid line {}'.format(line))

        text_lines = sorted(text_lines, key=lambda x: x['allrow'])

        if len(text_lines) == 0:
            logger.warning('{} is empty'.format(text_path))
    return text_lines


def load_pdf_pages(key):
    all_lines = load_pdf_pure_text_alltxt(key)
    pages = []
    if len(all_lines) == 0:
        return pages
    current_page_id = all_lines[0]['page']
    current_page = []
    for line in all_lines:
        if line['page'] == current_page_id:
            current_page.append(line)
        else:
            pages.append('\n'.join([t['inside'] for t in current_page]))
            current_page_id = line['page']
            current_page = [line]
    pages.append('\n'.join([t['inside'] for t in current_page]))
    return pages


if __name__ == '__main__':
    pdf_info = load_pdf_info()

    for key in pdf_info.keys():
        # key = '2021-03-23__苏州科达科技股份有限公司__603660__苏州科达__2020年__年度报告.pdf'
        print(key)
        pdf_pages = load_pdf_pages(key)
