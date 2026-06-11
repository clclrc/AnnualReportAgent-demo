import os
from datetime import datetime    # 时间处理
from loguru import logger     # 日志记录库
from config import cfg        # 导入项目配置文件
from file import download_data     # 数据下载函数
from company_table import count_table_keys, build_table   # 表格处理工具
from api_llm import ApiLLM, TaskType
from preprocess import extract_pdf_text, extract_pdf_tables   # PDF解析器
from check import init_check_dir, check_text, check_tables   # 数据验证工具
# 答案生成流水线
from generate_answer_with_classify import do_gen_keywords
from generate_answer_with_classify import do_classification, do_sql_generation, generate_answer, make_answer 
from project_meta import PROJECT_NAME, PROJECT_SUBTITLE

def check_paths():
    import ghostscript  # PDF处理底层依赖
    import camelot  # PDF表格提取库

    # 确保数据存储目录存在
    if not os.path.exists(cfg.DATA_PATH):  
        raise Exception('DATA_PATH not exists: {}'.format(cfg.DATA_PATH))
    # 确保xpdf工具存在
    if not os.path.exists(cfg.XPDF_PATH):  
        raise Exception('XPDF_PATH not exists: {}'.format(cfg.XPDF_PATH))
    else:  # 如果存在
        os.chdir(cfg.XPDF_PATH)  # 切换工作目录到XPDF路径
        os.system(f"chmod 755 {cfg.XPDF_PATH}/pdftotext")  # 确保可执行权限
        # 执行测试转换
        os.system(f'{cfg.XPDF_PATH}/pdftotext -table -enc UTF-8 {cfg.DATA_PATH}/check/test.pdf {cfg.DATA_PATH}/check/test.txt')
        # 读取并打印前10行
        with open(f'{cfg.DATA_PATH}/check/test.txt', 'r', encoding='utf-8') as f:
            print(f.readlines()[:10])
        print('Test xpdf success!')


    for task_name in ['classify', 'keywords', 'nl2sql', 'answer']:
        cfg.get_api_model(task_name)

    """
    for name in ['basic_info', 'employee_info', 'cbs_info', 'cscf_info', 'cis_info', 'dev_info']:
        table_path = os.path.join(cfg.DATA_PATH, '{}.json'.format(name))
        if not os.path.exists(table_path):
            raise Exception('table {} not exists: {}'.format(name, table_path))

    if not os.path.exists(os.path.join(cfg.DATA_PATH, 'CompanyTable.csv')):
        raise Exception('CompanyTable.csv not exists: {}'.format(os.path.join(cfg.DATA_PATH, 'CompanyTable.csv')))
    """
    
    print('Check paths success!')


if __name__ == '__main__':

    # 配置日志信息
    DATE = datetime.now().strftime('%Y%m%d')  # 将当前日期和时间格式化为字符串
    log_path = os.path.join(cfg.DATA_PATH, '{}.main.log'.format(DATE))  # 组合成文件路径，并格式化为20240229.main.log
    if os.path.exists(log_path): # 检查指定路径是否存在。
        os.remove(log_path)   #  删除指定路径的文件。
    logger.add(log_path, level='DEBUG')  # 为日志记录器添加一个新的日志文件。
    logger.info('启动项目: {} | {}'.format(PROJECT_NAME, PROJECT_SUBTITLE))

    # 检查目录数据是否齐全
    check_paths()

    # 1. 下载数据到data目录, 生成pdf_info.json
    download_data()

    # 2. 解析pdf, 提取相关数据
    extract_pdf_text()
    extract_pdf_tables()

    # 3. 检查一下数据, 缺失之类的
    init_check_dir()
    check_text(copy_error_pdf=True)
    check_tables(copy_error_pdf=True)

    # 4. 根据表中的字段生成总表
    # 对所有表格的行属性统计计数。
    count_table_keys()
    # 构建一个字典，键为所有pdf表格包含的所有字段属性，值为所有pdf对应的value
    build_table()

    # 5. 对问题进行分类
    model = ApiLLM(TaskType.Classify)
    # 对测试集问题进行分类，并将结果保存到csv文件中。
    do_classification(model)
    model.unload_model()

    # 6. 给问题生成keywords
    model = ApiLLM(TaskType.Keywords)
    # 对测试集问题进行关键词提取，并将结果保存到csv文件中。
    do_gen_keywords(model)
    model.unload_model()

    # 7. 对于统计类问题生成SQL
    model = ApiLLM(TaskType.NL2SQL)
    # 对测试集问题进行sql语句生成，并将结果保存到csv文件中。
    do_sql_generation(model)
    model.unload_model()

    # 8. 生成回答
    model = ApiLLM(TaskType.Nothing)
    generate_answer(model)

    # 9. 生成预测结果
    make_answer()
