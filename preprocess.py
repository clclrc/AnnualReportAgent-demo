import os
import json
import shutil
from multiprocessing import Pool
from loguru import logger
from config import cfg
from file import load_pdf_info
from pdf_util import PdfExtractor
from financial_state import (extract_basic_info, extract_employee_info,
    extract_cbs_info, extract_cscf_info, extract_cis_info, extract_dev_info, merge_info)

'''
切换工作目录到xpdf中，并赋予可执行权限
'''
def setup_xpdf():
    os.chdir(cfg.XPDF_PATH)
    cmd = 'chmod +x pdftotext'   # 确保 pdftotext 文件具有可执行权限
    os.system(cmd)    # 执行命令 cmd


'''
提取 PDF 文件中的纯文本内容
'''
def extract_pure_content(idx, key, pdf_path):
    #  记录日志信息，表示开始提取文本。
    logger.info('Extract text for {}:{}'.format(idx, key))  

    # 保存路径
    save_dir = os.path.join(cfg.DATA_PATH, cfg.PDF_TEXT_DIR)

    # 每个文件的保存路径
    key_dir = os.path.join(save_dir, key)

    if not os.path.exists(key_dir):
        os.mkdir(key_dir)
    save_path = os.path.join(key_dir, 'pure_content.txt')
    if os.path.exists(save_path):
        os.remove(save_path)

    # 使用 PdfExtractor 类的实例，调用 extract_pure_content_and_save 方法，提取 PDF 文件中的纯文本内容
    PdfExtractor(pdf_path).extract_pure_content_and_save(save_path)


'''
定义PDF文本提取入口函数
开启多线程处理所有pdf，并得到结果
'''
def extract_pdf_text(extract_func=extract_pure_content): # 可定制的提取函数（默认使用extract_pure_content）
    setup_xpdf()  # 切换工作目录到xpdf中，并赋予可执行权限

    # 创建输出目录
    save_dir = os.path.join(cfg.DATA_PATH, cfg.PDF_TEXT_DIR) 
    if not os.path.exists(save_dir):
       os.mkdir(save_dir)

    # 加载pdf_info数据到字典中
    pdf_info = load_pdf_info()

    # processes：并行进程数   starmap：将参数元组解包传递给函数
    # 创建一个进程池，指定进程数为 cfg.NUM_PROCESSES
    with Pool(processes=cfg.NUM_PROCESSES) as pool:

        # pool.starmap 返回一个列表，包含每个 extract_func 调用的结果。  
        # extract_func()  接受 (id,file_name,pdf文件路径)
        results = pool.starmap(extract_func, [(i, k, v['pdf_path']) for i, (k, v) in enumerate(pdf_info.items())])


'''
用于提取 PDF 文件中的有关公司，员工信息，资产负债，现金流量，利润表，研发表的表格信息，并分别合并保存为json文件。
'''
def extract_pdf_tables():

    # 加载 PDF 文件的信息，并获取所有 PDF 文件的键值
    pdf_info = load_pdf_info()
    pdf_keys = list(pdf_info.keys())

    

    
    # 创建一个进程池，指定进程数。
    # 并行调用函数，根据关键词信息，匹配满足条件的pdf表格，解析并保存为txt文件。
    # 所有子进程结果汇总到results列表中
    # basic_info
    with Pool(processes=cfg.NUM_PROCESSES) as pool:
        results = pool.map(extract_basic_info, pdf_keys)
    # 将所有pdf的 basic_info 表格信息合并到json文件中   公司基本信息
    merge_info('basic_info')
    # # employee_info   员工信息表
    with Pool(processes=cfg.NUM_PROCESSES) as pool:
        results = pool.map(extract_employee_info, pdf_keys)
    merge_info('employee_info')
    # cbs_info  资产负债表
    with Pool(processes=cfg.NUM_PROCESSES) as pool:
        results = pool.map(extract_cbs_info, pdf_keys)
    merge_info('cbs_info')
    # cscf_info  现金流量表
    with Pool(processes=cfg.NUM_PROCESSES) as pool:
        results = pool.map(extract_cscf_info, pdf_keys)
    merge_info('cscf_info')
    # cis_info  利润表
    with Pool(processes=cfg.NUM_PROCESSES) as pool:
        results = pool.map(extract_cis_info, pdf_keys)
    merge_info('cis_info')
    # dev_info  研发表
    with Pool(processes=cfg.NUM_PROCESSES) as pool:
        results = pool.map(extract_dev_info, pdf_keys)
    merge_info('dev_info')
