# -*- coding: utf-8 -*-
"""
sales_nlp_pipeline.py - 工业级销售文本 NLP 预处理与语义重塑流水线


处理流水线遵循：
① re 清洗 (表面噪声/无意义助词/特殊字符/中文数字规范化)
  ↓
② jieba 分词 (精确模式分词)
  ↓
③ 自定义领域词典 (动态注入商品库真实SKU/配件名/别名)
  ↓
④ 词性过滤 (POS 标注，锁定 m+q+n 语法序列)
  ↓
⑤ 关键词与要素提取 (分离主商品、订购量、折扣、延保、赠品)
  ↓
⑥ 语义还原与结构重构 (消除过度清洗粘连，产出标准提单与纯净检索 Query)
"""

import re
import os
import jieba
import jieba.posseg as pseg
import jieba.analyse
from typing import Dict, Any, List, Optional, Tuple

# 中文小写/口语数字转换表
CN_NUM = {
    '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '百': 100, '千': 1000
}

def chinese_to_arabic(text: str) -> str:
    """
    将文本中常见的中文口语数字/折扣转换为阿拉伯数字。
    例如：
      '五十台' -> '50台'
      '八八折' -> '8.8折'
      '八点八折' -> '8.8折'
      '两年' -> '2年'
      '一百台' -> '100台'
      '九折' -> '9.0折'
      '九五折' -> '9.5折'
    """
    # 1. 常见折扣模式：八八折 -> 8.8折，九折 -> 9.0折，九五折 -> 9.5折，八点八折 -> 8.8折
    def _disc_replace(m):
        d_str = m.group(1)
        if '点' in d_str:
            parts = d_str.split('点')
            v1 = CN_NUM.get(parts[0], 0)
            v2 = CN_NUM.get(parts[1], 0)
            return f"{v1}.{v2}折"
        if len(d_str) == 1:
            return f"{CN_NUM.get(d_str, 9)}.0折"
        if len(d_str) == 2:
            v1 = CN_NUM.get(d_str[0], 9)
            v2 = CN_NUM.get(d_str[1], 0)
            return f"{v1}.{v2}折"
        return m.group(0)

    res = re.sub(r'([一二两三四五六七八九点]+)\s*折', _disc_replace, text)

    # 2. 中文数字加量词：五十台 -> 50台, 两百盒 -> 200盒, 两年 -> 2年, 十台 -> 10台
    def _num_unit_replace(m):
        raw_cn = m.group(1)
        unit = m.group(2)
        # 简单转换十/百位数
        val = 0
        if raw_cn == '十':
            val = 10
        elif raw_cn.startswith('十'):
            val = 10 + CN_NUM.get(raw_cn[1], 0)
        elif '百' in raw_cn:
            parts = raw_cn.split('百')
            val = CN_NUM.get(parts[0], 1) * 100
            if len(parts) > 1 and parts[1]:
                if parts[1].startswith('十'):
                    val += 10 + (CN_NUM.get(parts[1][1], 0) if len(parts[1]) > 1 else 0)
                else:
                    val += CN_NUM.get(parts[1], 0)
        elif '十' in raw_cn:
            parts = raw_cn.split('十')
            val = CN_NUM.get(parts[0], 1) * 10 + (CN_NUM.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0)
        else:
            # 单字或多位连续数字如 '一五'
            mult = 1
            for ch in reversed(raw_cn):
                if ch in CN_NUM:
                    val += CN_NUM[ch] * mult
                    mult *= 10
        return f"{val} {unit}"

    res = re.sub(r'([零一二两三四五六七八九十百]+)\s*(台|部|盒|块|片|副|套|个|把|只|本|张|年)', _num_unit_replace, res)
    return res

class SalesNLPPipeline:
    """
    企业级销售提单自然语言预处理与重构流水线
    """
    _instance = None
    _dict_initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SalesNLPPipeline, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._dict_initialized:
            self._load_domain_dictionary()
            self._dict_initialized = True

    def _load_domain_dictionary(self):
        """
        ③ 注入企业级自定义专有词典，防止 jieba 把领域 SKU/配件名切碎
        """
        domain_terms = [
            # 核心商品实体及别名 (标注为 n_prod)
            ("AI算力显卡", 10000, "n_prod"),
            ("ai算力显卡", 10000, "n_prod"),
            ("算力显卡", 8000, "n_prod"),
            ("显卡", 6000, "n_prod"),
            ("RTX 5090", 10000, "n_prod"),
            ("5090", 8000, "n_prod"),
            ("远峰蓝苹果18", 10000, "n_prod"),
            ("苹果18", 9000, "n_prod"),
            ("mate70", 9000, "n_prod"),
            ("小米15", 9000, "n_prod"),
            ("990 PRO固态硬盘", 10000, "n_prod"),
            ("990 PRO", 8000, "n_prod"),
            ("固态硬盘", 8000, "n_prod"),
            ("希捷银河16T机械硬盘", 10000, "n_prod"),
            ("企业级交换机", 9000, "n_prod"),
            ("电竞鼠标垫", 8000, "n_prod"),
            # 核心 3C 品牌与笔记本品类词 (坚决防止品牌被切碎或被降级为泛词)
            ("华硕游戏笔记本", 10000, "n_prod"),
            ("华硕笔记本", 10000, "n_prod"),
            ("游戏笔记本", 9000, "n_prod"),
            ("华硕", 9000, "n_prod"),
            ("ROG", 9000, "n_prod"),
            ("枪神", 9000, "n_prod"),
            ("联想游戏笔记本", 10000, "n_prod"),
            ("联想笔记本", 10000, "n_prod"),
            ("拯救者", 9000, "n_prod"),
            ("Y9000P", 9000, "n_prod"),
            ("ThinkPad", 9000, "n_prod"),
            ("MacBook", 9000, "n_prod"),
            # 官方合法赠品与配件 (标注为 n_gift)
            ("拯救者 K7 客制化机械键盘", 10000, "n_gift"),
            ("客制化机械键盘", 9000, "n_gift"),
            ("机械键盘", 8000, "n_gift"),
            ("电竞鼠标", 8000, "n_gift"),
            ("ROG 铝合金 ARGB 发光重型显卡支架", 10000, "n_gift"),
            ("发光重型显卡支架", 9000, "n_gift"),
            ("显卡支架", 8000, "n_gift"),
            ("专属磁吸保护壳", 9000, "n_gift"),
            ("AR高透防爆钢化保护膜", 9000, "n_gift"),
            ("防爆钢化膜", 8000, "n_gift"),
            ("磁吸保护壳", 8000, "n_gift"),
            ("保护壳", 6000, "n_gift"),
            ("钢化膜", 6000, "n_gift"),
            ("碎屏险", 6000, "n_gift"),
            # 常见误输入的非法配件或生活品 (标注为 n_junk)
            ("防丢绳", 8000, "n_junk"),
            ("耳机套", 8000, "n_junk"),
            ("擦机布", 6000, "n_junk"),
            ("转接头", 6000, "n_junk"),
            # 业务动词与服务词
            ("延保", 9000, "n_serv"),
            ("质保", 9000, "n_serv"),
            ("保修", 9000, "n_serv"),
            ("申请打", 8000, "v_disc"),
            ("打折", 8000, "v_disc")
        ]

        for word, freq, tag in domain_terms:
            jieba.add_word(word, freq=freq, tag=tag)

        # 尝试动态从 DB 同步已有商品名 (采用项目统一的 psycopg 直连 PostgreSQL)
        try:
            import psycopg
            from dotenv import load_dotenv
            load_dotenv()
            db_uri = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db")
            with psycopg.connect(db_uri) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT product_name FROM products WHERE product_name IS NOT NULL;")
                    rows = cur.fetchall()
                    for r in rows:
                        if r[0]:
                            jieba.add_word(r[0].strip(), freq=10000, tag="n_prod")
        except Exception:
            pass

    def clean_noise(self, text: str) -> str:
        """
        ① re 正则浅层清洗（表面通用噪声去除与格式规范）
        """
        if not text:
            return ""

        # 1. 剔除 HTML 标签与 Markdown 符号
        s = re.sub(r'<[^>]+>', ' ', text)
        s = re.sub(r'[#\*\_~`【】\[\]（）\(\)]+', ' ', s)

        # 2. 规范中文数字与口语表达
        s = chinese_to_arabic(s)

        # 3. 剔除常见无意义口头前缀与客套话
        s = re.sub(r'^(?:【.*?】\s*)?(?:紧急采购|加急采购|紧急下单)?\s*(帮我下|帮我定|帮我拿|帮我们公司采购|我要买|我要下单|下单|请问|请帮我|采购|下)\s*', '帮我下 ', s)
        s = re.sub(r'(谢谢|急用|麻烦了|尽快发货|尽快)[!！\s]*$', '', s)

        # 4. 合并重复标点与多余空白
        s = re.sub(r'[,，!！;；、]+', '，', s)
        s = re.sub(r'\s+', ' ', s).strip()

        return s

    def parse_and_restore(self, raw_text: str) -> Dict[str, Any]:
        """
        工业级精准提炼：
        1. 绝不混淆主卖商品与随单赠品，精准切分主标的区与让利附赠区；
        2. 提炼主商品名称、订购数量、量词单位；
        3. 提炼折扣率与延保年数；
        4. 提炼赠品明细清单（名称、数量、量词）；
        5. 组装并返回工业标准结构化表单对象。
        """
        cleaned_text = self.clean_noise(raw_text)

        # 核心解耦：按让利让步关键词切分【主标的采购区】与【让利附赠区】
        split_match = re.split(r'(?:，|,)?\s*(?:并送|加送|外加送|送|附赠|赠送)\s*', cleaned_text, maxsplit=1)
        main_section = split_match[0]
        incentive_section = split_match[1] if len(split_match) > 1 else ""

        # 如果主区存在夹带配件（如 '帮我下 50 台显卡和 50 个防丢绳，申请8.8折'）
        mid_freebies = []
        fm_mid = re.search(r'(?:和|加|外加)\s*([0-9]+)\s*([个把只张套盒件部台片])\s*([^，,\s]+)', main_section)
        if fm_mid:
            mid_freebies.append({
                "name": fm_mid.group(3).strip(),
                "quantity": int(fm_mid.group(1)),
                "unit": fm_mid.group(2)
            })
            main_section = main_section[:fm_mid.start()] + main_section[fm_mid.end():]

        # 1. 主商品数量与量词 (从主标的区提取)
        quantity = 1
        unit = "台"
        qty_match = re.search(r'([0-9]+)\s*(台|部|盒|块|片|副|套|个|把|只|本|张)', main_section)
        if qty_match:
            quantity = int(qty_match.group(1))
            unit = qty_match.group(2)

        # 2. 折扣率提取
        disc_match = re.search(r'([0-9.]+)\s*折', cleaned_text)
        discount = float(disc_match.group(1)) / 10.0 if disc_match else 1.0
        discount_text = f"{disc_match.group(1)}折" if disc_match else "无折扣"
        discount_str = f"，申请打 {disc_match.group(1)} 折" if disc_match else ""

        # 3. 主卖商品核心名称 (绝对排除任何赠品干扰)
        # 清除前缀客套词、订购数量量词、折扣词、标点
        clean_main = re.sub(r'^(?:【.*?】\s*)?(?:紧急采购|加急采购|紧急下单)?\s*(帮我下|帮我定|采购|下单|下|帮我们公司采购|请帮我|请问|我要买)?\s*', '', main_section)
        clean_main = re.sub(r'([0-9]+)\s*(台|部|盒|块|片|副|套|个|把|只|本|张)', '', clean_main)
        clean_main = re.sub(r'申请打\s*[0-9.]+\s*折|申请\s*[0-9.]+\s*折|打\s*[0-9.]+\s*折|[0-9.]+\s*折', '', clean_main)
        clean_main = re.sub(r'(还有现货吗|现货吗|有现货吗|谢谢|急用|麻烦了|尽快发货|尽快)[!！\s]*$', '', clean_main).strip()
        clean_main = re.sub(r'[,，\s\?？!！]+', ' ', clean_main).strip()
        clean_main = re.sub(r'\b(急用|尽快|谢谢)\b', '', clean_main).strip()

        product_term = clean_main
        if not product_term or len(product_term) < 2:
            # POS 兜底
            words_with_flags = list(pseg.cut(main_section))
            for w, flag in words_with_flags:
                if flag in ["n_prod", "n", "nz", "nr"] and len(w) > 1 and w not in ["采购", "下单", "申请", "现货"]:
                    product_term = w
                    break
        if not product_term:
            product_term = "商品"

        # 4. 延保期限提取 (从让利区或全句中提取)
        warranty_match = re.search(r'(?:送|附赠|赠送|包含|质保|保修).*?([0-9]+)\s*年(?:延保|保修|质保)?', cleaned_text)
        if not warranty_match:
            warranty_match = re.search(r'([0-9]+)\s*年\s*(?:延保|保修|质保)?', incentive_section if incentive_section else cleaned_text)

        has_warranty = warranty_match is not None
        warranty_years = int(warranty_match.group(1)) if warranty_match else (1 if ("延保" in cleaned_text or "质保" in cleaned_text) else 0)

        # 5. 赠送商品明细提取 (从让利区精准抽取完整赠品名称，支持带型号如 '拯救者 K7 客制化机械键盘')
        freebies: List[Dict[str, Any]] = list(mid_freebies)
        if incentive_section:
            # 先剥离延保部分，剩余全部属于赠品子句
            inc_without_war = re.sub(r'[0-9]+\s*年\s*(?:延保|质保|保修)?', '', incentive_section)
            # 按标点或并列词分割各赠品项
            freebie_clauses = re.split(r'[,，、]|(?<=[^\s])\s*(?:和|以及|加|外加)\s*', inc_without_war)
            for clause in freebie_clauses:
                clause = clause.strip()
                if not clause:
                    continue
                # 去除前缀连接词与动词 (包含开头的 '和'、'送' 等)
                clause = re.sub(r'^(?:和|以及|加|外加|送|附赠|赠送|包含|加送|附带)\s*', '', clause).strip()
                if not clause:
                    continue
                # 提取赠品专属数量与量词
                qm = re.search(r'^([0-9]+)\s*([个把只张套盒件部台片])?\s*', clause)
                if qm:
                    fq = int(qm.group(1))
                    fu = qm.group(2) or "个"
                    fn = clause[qm.end():].strip()
                else:
                    fq = quantity  # 默认 1:1 或 1
                    fu = "个"
                    fn = clause
                
                # 再次清理 fn 开头的连词或符号
                fn = re.sub(r'^(?:和|以及|加|外加|个|把|只|张|套|盒|件|部|台|片)\s*', '', fn).strip()
                
                # 过滤掉非实质赠品词
                if fn and not any(k in fn for k in ["折", "延保", "保修", "质保"]) and len(fn) >= 2 and fn != product_term:
                    freebies.append({
                        "name": fn,
                        "quantity": fq,
                        "unit": fu
                    })

        # 6. 语义还原提单基干 (完全剥离任何非主商品杂质)
        clean_base_text = f"帮我下 {quantity} {unit} {product_term}{discount_str}"

        # 7. 组装标准工业级结构化表单对象
        structured_proposal_form = {
            "main_product": {
                "product_name": product_term,
                "quantity": quantity,
                "unit": unit
            },
            "freebie_items": [
                {
                    "freebie_name": fb["name"],
                    "quantity": fb["quantity"],
                    "unit": fb["unit"]
                }
                for fb in freebies
            ],
            "discount_info": {
                "has_discount": disc_match is not None,
                "discount_rate": discount,
                "discount_text": discount_text
            },
            "warranty_info": {
                "has_warranty": has_warranty,
                "warranty_years": warranty_years,
                "warranty_text": f"{warranty_years}年延保" if has_warranty else "无延保"
            },
            "raw_input": raw_text,
            "cleaned_text": cleaned_text,
            
            # 向下完全兼容原有字段
            "product_term": product_term,
            "clean_query": product_term,
            "quantity": quantity,
            "unit": unit,
            "discount": discount,
            "has_warranty": has_warranty,
            "warranty_years": warranty_years if has_warranty else 1,
            "claimed_freebies": freebies,
            "freebie_list": freebies,
            "clean_base_text": clean_base_text
        }

        return structured_proposal_form

    def extract_structured_form(self, raw_text: str) -> Dict[str, Any]:
        """专门用于提炼销售意图并返回纯粹标准结构化表单的业务API"""
        res = self.parse_and_restore(raw_text)
        return {
            "main_product": res["main_product"],
            "freebie_items": res["freebie_items"],
            "discount_info": res["discount_info"],
            "warranty_info": res["warranty_info"],
            "clean_query": res["clean_query"]
        }

# 全局单例
nlp_pipeline = SalesNLPPipeline()
