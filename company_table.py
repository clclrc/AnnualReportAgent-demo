import re
import os
from collections import Counter
import json
import sqlite3
import numpy as np
import pandas as pd

from config import cfg
from file import load_pdf_info, load_tables_of_years
from file import load_total_tables

_COMPANY_TABLE_CACHE = None
_SQL_CONN = None
_SQL_CURSOR = None


"""
统计所有PDF文件中表格数据的键（行名）出现频次，保存为JSON文件
"""
def count_table_keys():
    # 加载pdf_info信息
    pdf_info = load_pdf_info()
    # 加载总表格   key (basic/employee/...)：所有pdf的表格内容
    all_tables = load_total_tables()
    
    # 存储所有表格行名
    all_keys = []

    for pdf_key, pdf_item in list(pdf_info.items()):
        # print(pdf_key)
        company = pdf_item['company']
        year = pdf_item['year'].replace('年', '')
        # 根据公司，年份，加载结构化元组表格
        table = load_tables_of_years(company, [year], all_tables, pdf_info)
        # 提取表格中的属性名
        row_names = list(set([t[2] for t in table]))
        all_keys.extend(row_names)
    # 对所有属性名进行计数
    all_keys = Counter(all_keys)
    # 写入文件
    with open(os.path.join(cfg.DATA_PATH, 'key_count.json'), 'w', encoding='utf-8') as f:
        json.dump(all_keys, f, ensure_ascii=False, indent=4)

'''
构建结构化公司信息表格，筛选高频字段并导出为CSV
'''
def build_table(min_ratio=0.1):
    pdf_info = load_pdf_info()  # 加载PDF元数据（公司名、年份、路径等）
    all_tables = load_total_tables()  # 加载所有PDF解析后的表格数据

    with open(os.path.join(cfg.DATA_PATH, 'key_count.json'), 'r', encoding='utf-8') as f:
        key_count = json.load(f)  # 读取字段出现次数字典（格式：{"总资产": 238, "净利润": 193}）
    
    max_count = max(key_count.values()) # 计算最高频次
    key_count = sorted(key_count.items(), key=lambda x: x[1], reverse=True) # 按频次降序排序
    used_keys = [key for key, count in key_count if count > min_ratio * max_count]  # 示例：若 max_count=1000，min_ratio=0.1 → 保留出现超过 100 次的字段

    # 固定列 + 筛选字段
    columns = ['公司全称', '年份'] + used_keys
    df_dict = {}  # 数据存储字典
    for col in columns:
        df_dict[col] = []  # 每个初始化为空列表

    # 加载当前PDF的表格数据（返回格式：[ (表名,年份,字段名,值), ... ]）
    for pdf_key, pdf_item in list(pdf_info.items()):
        # if pdf_key != '2020-04-22__比亚迪股份有限公司__002594__比亚迪__2019年__年度报告.pdf':
        #     continue
        company = pdf_item['company']
        year = pdf_item['year'].replace('年', '')
        # 根据公司，年份，加载结构化元组表格
        table = load_tables_of_years(company, [year], all_tables, pdf_info)
        
        df_dict['公司全称'].append(company)
        df_dict['年份'].append(year)

        # 遍历所有字段
        for key in used_keys:
            value = 'NULLVALUE'
            # 遍历当前PDF的所有字段数据
            for table_name, year, row_name, row_value in table:
                if year != year:
                    continue
                if row_name == key:  # 匹配目标字段
                    value = row_value
                    break   # 找到第一个匹配值即停止
            # 数据清洗（移除单位字符）
            value = value.replace('人', '').replace('元', '').replace(' ', '')
            df_dict[key].append(value)
    # 保存结果到csv中
    pd.DataFrame(df_dict).to_csv(os.path.join(cfg.DATA_PATH, 'CompanyTable.csv'), sep='\t', index=False, encoding='utf-8')

'''
用于加载公司数据表
'''
def load_company_table():
    global _COMPANY_TABLE_CACHE
    if _COMPANY_TABLE_CACHE is not None:
        return _COMPANY_TABLE_CACHE.copy()
    df_path = os.path.join(cfg.DATA_PATH, 'CompanyTable.csv')
    # 读取 CSV 文件
    df = pd.read_csv(df_path, sep='\t', encoding='utf-8')# 指定分隔符为制表符
    # 为 DataFrame df 添加一个新列 'key'，其值由 '公司全称' 和 '年份' 列拼接而成。
    df['key'] = df.apply(lambda t: t['公司全称'] + str(t['年份']), axis=1)
    # 加载 PDF 文件的相关信息
    pdf_info = load_pdf_info()
    # 遍历 pdf_info 的值，生成公司键值列表。
    company_keys = [v['company'] + v['year'].replace('年', '').replace(' ', '') for v in pdf_info.values()]
    # 筛选 DataFrame df，只保留 'key' 列的值在 company_keys 列表中的行。
    df = df[df['key'].isin(company_keys)]
    # 删除 'key' 列
    del df['key']
    # 返回DataFrame
    _COMPANY_TABLE_CACHE = df
    return df.copy()

'''
用于将输入值 t 转换为数值类型。
'''
def col_to_numeric(t):
    try:
        value = float(t)  # 尝试将输入值 t 转换为浮 点数。
        if value > 2**63 - 1:  # 检查转换后的数值是否超过 2**63 - 1 （即 64 位有符号整数的最大值）。
            return np.nan   # 如果数值超过范围，返回 np.nan（Not a Number，表示缺失值）。
        elif int(value) == value:  # 检查浮点数是否可以表示为整数。如果浮点数等于其整数部分，返回整数值。
            return int(value)
        else:
            return float(t)  # 如果数值在范围内且不是整数，返回原始的浮点数值。
    except:
        return np.nan

'''
这段代码定义了一个函数 get_sql_search_cursor，用于创建一个 SQLite 内存数据库，并将一个 DataFrame 转换为数据库表
'''
def get_sql_search_cursor():
    global _SQL_CONN
    global _SQL_CURSOR
    if _SQL_CURSOR is not None:
        return _SQL_CURSOR
    # 使用 sqlite3.connect 创建一个 SQLite 数据库连接，连接到内存数据库
    conn = sqlite3.connect(':memory:') 
    # build_table()

    # 加载公司数据表
    df = load_company_table()
    # 初始化一个空字典 dtypes，用于存储每个列的数据类型。
    dtypes = {}
    # 遍历 DataFrame df 的每一列。
    for col in df.columns:   # 统计当前列中数值型数据的比例。
        num_count = 0  # 数值型数据的计数。
        tot_count = 0  # 总数据计数。
        for v in df[col]: 
            if v == 'NULLVALUE':
                continue
            tot_count += 1
            try:
                number = float(v)
            except ValueError:
                continue
            num_count += 1  # 尝试将值转换为浮点数，如果成功则增加 num_count
        # 如果总数据计数大于 0 且数值型数据比例大于 50%，则将列类型设置为 REAL，否则设置为 TEXT。
        if tot_count > 0 and num_count / tot_count > 0.5:  
            df[col] = df[col].apply(lambda t: col_to_numeric(t)).replace([np.inf, -np.inf], np.nan)
            dtypes[col] = 'REAL'
        else:
            dtypes[col] = 'TEXT'
    
    dtypes['年份'] = 'TEXT'
    # 将 DataFrame 保存到数据库
    df.to_sql(name='company_table', con=conn, if_exists='replace', dtype=dtypes)
    # 创建游标对象，用于执行 SQL 查询
    cursor = conn.cursor()
    _SQL_CONN = conn
    _SQL_CURSOR = cursor
    return _SQL_CURSOR


def get_search_result(cursor, query):
    result = cursor.execute(query)
    return result



def get_cn_en_key_map(model, keys):
    def get_en_key(cn_key):
        prompt = '''
    你的任务是将中文翻译为英文短语。
    注意：
    1. 你只需要回答英文短语，不要进行解释或者回答其他内容。
    2. 尽可能简短的回答。
    3. 你输出的格式是:XXX对应的英文短语是XXXXX。
    -----------------------
    需要翻译的中文为：{}
    '''.format(cn_key)
        en_key = model(prompt)
        print(en_key)
        en_key = ' '.join(re.findall('[ a-zA-Z]+', en_key)).strip(' ').split(' ')
        en_key = [w[0].upper() + w[1:] for w in en_key if len(w)>1]
        en_key = '_'.join(en_key)
        return en_key
    en_keys = [get_en_key(key) for key in keys]
    key_map = dict(zip(keys, en_keys))
    with open(os.path.join(cfg.DATA_PATH, 'key_map.json'), 'w', encoding='utf-8') as f:
        json.dump(key_map, f, ensure_ascii=False, indent=4)


def load_cn_en_key_map():
    with open(os.path.join(cfg.DATA_PATH, 'key_map.json'), 'r', encoding='utf-8') as f:
        key_map = json.load(f)
    return key_map


def check_company_table():
    df = load_company_table()

    df['key'] = df.apply(lambda t: t['公司全称'] + str(t['年份']), axis=1)

    with open(os.path.join(cfg.DATA_PATH, 'B-pdf-name.txt'), 'r', encoding='utf-8') as f:
        pdf_names = [t.strip() for t in f.readlines()]
    pdf_info = load_pdf_info()
    B_pdf_keys = []
    for pdf_name, pdf_item in pdf_info.items():
        if pdf_name not in pdf_names:
            continue
        B_pdf_keys.append(pdf_item['company'] + pdf_item['year'].replace('年', ''))
    print(B_pdf_keys[:10])
    # df = df[df['key'].isin(B_pdf_keys)]

    cols = ['公司全称', '年份', '其他非流动资产', '利润总额', '负债合计', '营业成本',
        '注册地址', '流动资产合计', '营业收入', '货币资金', '资产总计']

    df.loc[:, cols].to_csv(os.path.join(cfg.DATA_PATH, 'B_CompanyTable.csv'), index=False, sep='\t', encoding='utf-8')
 

if __name__ == '__main__':
    count_table_keys()
    build_table()
