import os
import json
import shutil  # 高级文件操作：文件复制/删除/移动等
import tempfile  # 安全创建临时文件和目录
import pdfplumber
import camelot   # PDF表格提取专用库（支持线检测和流模式）
import re
import numpy as np
from loguru import logger
from multiprocessing import Pool  # 进程池并行处理

from config import cfg


class PdfExtractor(object):

    def __init__(self, path) -> None:
        self.path = path

    # 表示是否使用 xpdf 工具进行文本提取，默认 use_xpdf=True
    def extract_pure_content_and_save(self, save_path, use_xpdf=True):  
        try:
            pdf = pdfplumber.open(self.path) # 使用 pdfplumber 打开 PDF 文件。
        except Exception as e:
            print(e)
            return

        # 如果不使用 xpdf 工具，则使用 pdfplumber 提取文本并保存。
        if not use_xpdf:
            with open(save_path, 'w', encoding='utf-8') as f:
                # 遍历 PDF 文件的每一页。
                for page in pdf.pages:
                    # 提取当前页的文本内容。
                    text = page.extract_text()
                    line = {
                        'page': page.page_number,
                        'text': text
                    }
                    # print(text)
                    f.write(json.dumps(line, ensure_ascii=True) + '\n')
        else:# 如果使用 xpdf 工具
            # 命令行执行文件进行转化。
            os.chdir(cfg.XPDF_PATH)
            cmd = './pdftotext -table -enc UTF-8 "{}" "{}"'.format(
                    self.path, save_path)
            os.system(cmd)
            
            # 以读取模式打开 save_path 文件，编码为 utf-8，忽略编码错误
            with open(save_path, 'r', encoding='utf-8', errors='ignore') as f: # 
                lines = f.readlines()  # 读取文件的所有行
                # 将所有行连接为一个字符串，并按页分割符 \x0c 分割成页面列表。
                pages = '\n'.join(lines).split('\x0c')  
            
            # 检查 PDF 文件的页数是否与提取的页数匹配
            if len(pdf.pages) != len(pages) - 1:
                logger.error('{} {} does not match for {}'.format(len(pdf.pages), len(pages), self.path))
            
            # 保存处理后的文本
            with open(save_path, 'w', encoding='utf-8') as f:
                for idx, page in enumerate(pages):
                    lines = page.split('\n')
                    lines = [line for line in lines if len(line.strip()) > 0]
                    page_block = {
                        'page': idx+1,
                        'text': '\n'.join(lines)
                    }
                    f.write(json.dumps(page_block, ensure_ascii=False) + '\n')
        pdf.close()

    '''
    传入pdf的页数范围，解析该范围的表格内容
    '''
    def extract_table_of_pages(self, page_ids: list):
        '''
            this method is slow
        '''
        if True:
            with tempfile.TemporaryDirectory() as temp_dir: # 创建自动清理的临时目录
                if not self.path.endswith('.pdf'):
                    temp_path = os.path.join(temp_dir, '{}.pdf'.format(os.path.basename(self.path)))
                    shutil.copy(self.path, temp_path)  # 非PDF文件复制为PDF格式
                else:
                    temp_path = self.path  # 直接使用原始PDF路径
                try:
                    tables = camelot.read_pdf(
                        temp_path,
                        strip_text='\n',  # 删除单元格内换行符
                        pages=','.join(map(str, page_ids)),  # 格式化为"1,3,5"的页面参数
                        line_tol=6,  # 线合并容差（单位：像素）
                        line_scale=60)  # 线检测灵敏度（值越大检测更细的线）
                except IndexError:  # 捕获无效页面访问异常
                    tables = []
                
                # check chaos tables
                num_chaos = 0
                # 遍历所有表格
                for table in tables:
                    for _, row in table.df.iterrows(): # 遍历所有行
                        for v in row.values:   # 遍历单元格
                            # 正常数值应有 ≤1 个小数点（如 123.45）若单元格出现多个小数点（如 12.34.56），可能意味着：表格解析错误（如文本错误拆分到多个列）
                            point_num = list(v).count('.' )  # 统计小数点数量  
                            num_chaos = max(point_num, num_chaos)  # 记录最大异常值
                # print(num_chaos, '--')

                # 当检测到严重格式混乱时，改用流模式（stream）重新解析表格
                if len(tables) == 0 or num_chaos > 5:
                    tables = camelot.read_pdf(
                        temp_path,
                        pages=','.join(map(str, page_ids)),
                        flavor='stream', 
                        edge_tol=100) # 放宽单元格边界检测阈值
                if False:
                    for table in tables:
                        print(table.page)
                        import matplotlib.pyplot as plt
                        camelot.plot(table, kind='grid').show()
                        plt.show()
                        for _, row in table.df.iterrows():
                            print(row.values)
        else:
            
            tables = camelot.read_pdf(self.path,
                    strip_text='\n',
                    pages=','.join(map(str, page_ids)),
                    line_scale=60, copy_text=['v', 'h'])
            print(tables)
            for table in tables:
                print(table.df.to_string())
                print(table._bbox)
            # import matplotlib.pyplot as plt
            # camelot.plot(tables[0], kind='text')
            # plt.show()
        return tables

    def extract_table_of_pages_pdfplumber(self, page_ids: list):
        pdf = pdfplumber.open(self.path)
        
        tables = []
        for i, page in enumerate(pdf.pages):
            if page.page_number not in page_ids:
                continue

            page = page.filter(self.keep_visible_lines)
            
            edges = self.curves_to_edges(page.curves + page.edges)
            if len(edges) > 0:
                table_settings = {
                    "vertical_strategy": "explicit",
                    "horizontal_strategy": "explicit",
                    "explicit_vertical_lines": self.curves_to_edges(page.curves + page.edges),
                    "explicit_horizontal_lines": self.curves_to_edges(page.curves + page.edges),
                    "intersection_y_tolerance": 3,
                    'snap_tolerance': 3,
                }
            else:
                table_settings = {
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    'snap_tolerance': 3,
                }
            
            # Get the bounding boxes of the tables on the page.
            plumber_tables = page.find_tables(table_settings=table_settings)
            tables.extend([self.get_text(t) for t in plumber_tables])

        for table in tables:
            print(table)

        return tables
        

    @staticmethod
    def keep_visible_lines(obj):
        """
        If the object is a ``rect`` type, keep it only if the lines are visible.

        A visible line is the one having ``non_stroking_color`` not null.
        """
        if obj['object_type'] == 'rect':
            if obj['non_stroking_color'] is None:
                return False
            if obj['width'] < 1 and obj['height'] < 1:
                return False
            # return obj['width'] >= 1 and obj['height'] >= 1 and obj['non_stroking_color'] is not None
        if obj['object_type'] == 'char':
            return obj['stroking_color'] is not None and obj['non_stroking_color'] is not None
        return True
    
    @staticmethod
    def curves_to_edges(cs):
        """See https://github.com/jsvine/pdfplumber/issues/127"""
        edges = []
        for c in cs:
            edges += pdfplumber.utils.rect_to_edges(c)
        return edges
    
    @staticmethod
    def not_within_bboxes(obj, bboxes):
        """Check if the object is in any of the table's bbox."""
        def obj_in_bbox(_bbox):
            """See https://github.com/jsvine/pdfplumber/blob/stable/pdfplumber/table.py#L404"""
            v_mid = (obj["top"] + obj["bottom"]) / 2
            h_mid = (obj["x0"] + obj["x1"]) / 2
            x0, top, x1, bottom = _bbox
            return (h_mid >= x0) and (h_mid < x1) and (v_mid >= top) and (v_mid < bottom)
        return not any(obj_in_bbox(__bbox) for __bbox in bboxes)
    
    @staticmethod
    def get_top(obj):
        if isinstance(obj, pdfplumber.table.Table):
            return obj.bbox[1]
        if isinstance(obj, dict):
            return obj['top']
    
    @staticmethod
    def get_text(obj):
        if isinstance(obj, pdfplumber.table.Table):
            table_text = obj.extract()
            table_text = [[t if t is not None else 'NULL' for t in row] for row in table_text]
            table_text = [[t.replace('\n', '').replace(' ', '') for t in row] for row in table_text]
            table_text = [[t if t!='' else 'NULL' for t in row] for row in table_text]
            text = '\n'
            if len(table_text) == 0:
                return text
            num_cols = len(table_text[0])
            seps = ['---' for _ in range(num_cols)]
            if len(table_text) > 1:
                table_text.insert(1, seps)
            for row in table_text:
                text += '| {} |\n'.format(' | '.join(row))
            text += '\n'
            return text
        if isinstance(obj, dict):
            text = obj['text'].replace(' ', '').replace('\n', '')
            if len(text) == 0:
                return ''
            else:
                return text + '\n'
