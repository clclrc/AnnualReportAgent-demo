import os
import shutil
from config import cfg
from file import load_pdf_info, load_pdf_pure_text, load_pdf_tables, load_total_tables


'''
构建错误PDF存储路径
'''
def init_check_dir():
    check_dir = os.path.join(cfg.DATA_PATH, cfg.ERROR_PDF_DIR)
    # 清理旧目录（如果存在）
    if os.path.exists(check_dir):
        shutil.rmtree(check_dir)
    # 创建空目录
    os.mkdir(check_dir)

'''
检查PDF文本内容有效性，复制无文本的PDF到错误目录
'''
def check_text(copy_error_pdf=True):
    pdf_info = load_pdf_info()
    
    check_dir = os.path.join(cfg.DATA_PATH, cfg.ERROR_PDF_DIR)

    for k, v in pdf_info.items():
        # 提取pdf文本内容
        text_lines = load_pdf_pure_text(k)
        if len(text_lines) == 0 and copy_error_pdf:
            dst_path = os.path.join(check_dir, 'TextError_{}.pdf'.format(k))
            if not os.path.exists(dst_path): # 防重复复制：避免覆盖已有文件
                shutil.copy(v['pdf_path'], dst_path)

'''
检查PDF表格内容有效性，复制无文本的PDF到错误目录
'''
def check_tables(copy_error_pdf=True):
    # 加载pdf信息info
    pdf_info = load_pdf_info()
    # 加载所有pdf 表格key和context
    all_tables = load_total_tables()
    # 检查错误目录
    check_dir = os.path.join(cfg.DATA_PATH, cfg.ERROR_PDF_DIR)
    
    # 遍历pdf_info表
    for k, v in pdf_info.items():
        tables = load_pdf_tables(k, all_tables)
        for name, table in tables.items():
            if len(table) == 0 and copy_error_pdf:
                dst_path = os.path.join(check_dir, 'TableError_{}_{}.pdf'.format(name, k))
                if not os.path.exists(dst_path):
                    shutil.copy(v['pdf_path'], dst_path)
                
