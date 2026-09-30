"""
3C 智能终端与企业级电子设备专属赠品绑定规则与品类矩阵
"""
import re
from typing import Dict, List, Optional, Any

# 1. 权威品类赠品配置矩阵
# freebie_type: "single" | "multiple" | "none"
CATEGORY_FREEBIE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "GPU": {
        "category_name": "独立显卡",
        "category_code": "A",
        "freebie_type": "single",
        "default_freebie": "ROG 铝合金 ARGB 发光重型显卡支架",
        "default_cost": 65.0,
        "allowed_freebies": [
            {"name": "ROG 铝合金 ARGB 发光重型显卡支架", "alias": ["显卡支架", "发光支架", "重型支架", "支架"], "unit_cost": 65.0, "unit": "个"}
        ],
        "keywords": ["显卡", "rtx", "5090", "5080", "7900", "geforce", "radeon"]
    },
    "EARPHONE": {
        "category_name": "无线蓝牙耳机",
        "category_code": "C",
        "freebie_type": "single",
        "default_freebie": "AirPods/FreeBuds 液体硅胶防摔保护套 (带金属挂钩)",
        "default_cost": 15.0,
        "allowed_freebies": [
            {"name": "液体硅胶防摔保护套", "alias": ["耳机保护套", "硅胶保护套", "保护套", "耳机套"], "unit_cost": 15.0, "unit": "个"}
        ],
        "keywords": ["耳机", "airpods", "freebuds", "1000xm5", "降噪豆"]
    },
    "TABLET": {
        "category_name": "智能平板",
        "category_code": "B",
        "freebie_type": "single",
        "default_freebie": "iPad 专属磁吸多角度双面保护套",
        "default_cost": 45.0,
        "allowed_freebies": [
            {"name": "磁吸双面保护套", "alias": ["平板保护套", "保护套", "皮套"], "unit_cost": 45.0, "unit": "个"}
        ],
        "keywords": ["ipad", "平板", "pad"]
    },
    "PHONE": {
        "category_name": "旗舰智能手机",
        "category_code": "B",
        "freebie_type": "multiple",
        "allowed_freebies": [
            {"name": "芳纶纤维磁吸防摔保护壳", "alias": ["手机壳", "保护壳", "手机套", "壳"], "unit_cost": 45.0, "unit": "个"},
            {"name": "AR高透防爆钢化保护膜", "alias": ["钢化膜", "防爆膜", "防窥膜", "保护膜", "膜"], "unit_cost": 10.0, "unit": "张"},
            {"name": "倍思 140W 氮化镓超级快充套装", "alias": ["快充套装", "快充头", "快充", "充电器"], "unit_cost": 85.0, "unit": "套"}
        ],
        "keywords": ["手机", "苹果18", "mate70", "小米15", "iphone", "pro max", "远峰蓝", "羽砂黑"]
    },
    "LAPTOP": {
        "category_name": "笔记本电脑",
        "category_code": "D",
        "freebie_type": "multiple",
        "allowed_freebies": [
            {"name": "拯救者 K7 客制化机械键盘", "alias": ["机械键盘", "客制化键盘", "电竞键盘", "键盘"], "unit_cost": 160.0, "unit": "把"},
            {"name": "罗技 MX Master 3S / 电竞无线鼠标", "alias": ["无线鼠标", "电竞鼠标", "蓝牙鼠标", "鼠标"], "unit_cost": 110.0, "unit": "只"},
            {"name": "拯救者多功能防震双肩电脑包", "alias": ["双肩包", "电脑包", "背包", "内胆包"], "unit_cost": 55.0, "unit": "个"}
        ],
        "keywords": ["笔记本", "thinkpad", "拯救者", "macbook", "枪神", "电脑", "商务本", "游戏本"]
    },
    "DIY_HARDWARE": {
        "category_name": "DIY电脑硬件散件",
        "category_code": "E",
        "freebie_type": "none",
        "allowed_freebies": [],
        "note": "DIY 硬件散件严格禁止赠送任何赠品配件，仅支持商业延保",
        "keywords": ["固态", "机械硬盘", "990 pro", "exos", "硬盘", "ssd", "nvme", "cpu", "处理器", "intel", "酷睿", "i7", "i9", "ultra 9", "amd", "锐龙", "9950x", "散热", "水冷", "风冷", "主板", "电源"]
    },
    "ENTERPRISE_IT": {
        "category_name": "企业级IT设备",
        "category_code": "F",
        "freebie_type": "none",
        "allowed_freebies": [],
        "note": "企业级 IT 设备严格禁止赠送消费级配件，仅支持商业延保",
        "keywords": ["交换机", "服务器", "catalyst", "poweredge"]
    }
}

def detect_category_rule(text: str) -> Dict[str, Any]:
    """根据输入的商品名或提单语句准确识别主标的商品所属品类规则"""
    t = (text or "").lower()
    
    # 1. 尝试截取前半段的主商品名称（去除“送...”、“赠送...”、“申请打...折”等让利语句）
    main_target = re.split(r'，|,|申请|送|附赠|打[0-9.]*折', t)[0]
    # 如果前半段过短，则参考全文
    eval_text = main_target if len(main_target) >= 4 else t
    
    # 2. 精确主品类识别 (按具体特征优先级匹配)
    # A. 独立显卡
    if any(k in eval_text for k in ["显卡", "rtx", "5090", "5080", "7900", "geforce", "radeon"]):
        return {"category_key": "GPU", **CATEGORY_FREEBIE_CONFIGS["GPU"]}
        
    # B. 蓝牙无线耳机
    if any(k in eval_text for k in ["耳机", "airpods", "freebuds", "1000xm5", "降噪豆"]):
        return {"category_key": "EARPHONE", **CATEGORY_FREEBIE_CONFIGS["EARPHONE"]}
        
    # C. 笔记本电脑
    if any(k in eval_text for k in ["笔记本", "thinkpad", "拯救者", "macbook", "枪神", "电脑", "商务本", "游戏本"]):
        return {"category_key": "LAPTOP", **CATEGORY_FREEBIE_CONFIGS["LAPTOP"]}
        
    # D. 智能平板
    if any(k in eval_text for k in ["ipad", "平板", "pad"]):
        return {"category_key": "TABLET", **CATEGORY_FREEBIE_CONFIGS["TABLET"]}
        
    # E. DIY 核心散件 (固态/硬盘/散热/CPU/主板/电源)
    if any(k in eval_text for k in ["固态", "机械硬盘", "990 pro", "exos", "硬盘", "ssd", "nvme", "cpu", "处理器", "intel", "酷睿", "i7", "i9", "ultra 9", "amd", "锐龙", "9950x", "散热", "水冷", "风冷", "主板", "电源"]):
        return {"category_key": "DIY_HARDWARE", **CATEGORY_FREEBIE_CONFIGS["DIY_HARDWARE"]}
        
    # F. 企业级 IT
    if any(k in eval_text for k in ["交换机", "服务器", "catalyst", "poweredge"]):
        return {"category_key": "ENTERPRISE_IT", **CATEGORY_FREEBIE_CONFIGS["ENTERPRISE_IT"]}
        
    # G. 旗舰手机 (仅当主品明确提到手机或代表机型时，避免赠品“手机壳”串扰)
    if any(k in eval_text for k in ["苹果18", "mate70", "小米15", "iphone", "pro max", "远峰蓝", "羽砂黑", "暗夜紫"]) or ("手机" in eval_text and "壳" not in eval_text and "套" not in eval_text):
        return {"category_key": "PHONE", **CATEGORY_FREEBIE_CONFIGS["PHONE"]}
        
    # 全文再查一次 (如果前半段没能匹配到)
    if any(k in t for k in ["显卡", "rtx", "5090", "5080", "7900"]):
        return {"category_key": "GPU", **CATEGORY_FREEBIE_CONFIGS["GPU"]}
    if any(k in t for k in ["固态", "机械硬盘", "990 pro", "exos", "硬盘", "ssd", "cpu", "处理器", "散热器"]):
        return {"category_key": "DIY_HARDWARE", **CATEGORY_FREEBIE_CONFIGS["DIY_HARDWARE"]}
    if any(k in t for k in ["苹果18", "mate70", "小米15"]):
        return {"category_key": "PHONE", **CATEGORY_FREEBIE_CONFIGS["PHONE"]}
            
    # 默认兜底散件无赠品
    return {
        "category_key": "OTHER",
        "category_name": "其他商品",
        "category_code": "Z",
        "freebie_type": "none",
        "allowed_freebies": [],
        "keywords": []
    }

def inspect_proposal_elements(sales_input: str) -> Dict[str, Any]:
    """
    检查销售自然语言提单的要素完整性：
    - 前置采用 NLP 预处理流水线（re清洗 -> jieba精确分词 -> 专有词典 -> POS序列 -> 语义还原）
    - 剥离夹杂的各种非主商品非法赠品与噪声
    - 检查订购数量、延保年数与合规赠品
    - 决定是否需要前端弹窗提醒
    """
    from sales_nlp_pipeline import nlp_pipeline
    
    # 1. 运行工业级 NLP 预处理流水线
    nlp_res = nlp_pipeline.parse_and_restore(sales_input)
    cleaned_input = nlp_res["cleaned_text"]
    product_term = nlp_res["product_term"]
    quantity = nlp_res["quantity"]
    unit = nlp_res["unit"]
    discount = nlp_res["discount"]
    has_warranty = nlp_res["has_warranty"]
    warranty_years = nlp_res["warranty_years"]
    clean_base_text = nlp_res["clean_base_text"]

    # 2. 基于纯净商品名与清洗后文本判定权威品类
    cat_info = detect_category_rule(product_term if len(product_term) >= 2 else cleaned_input)
    freebie_type = cat_info["freebie_type"]
    
    # 3. 检查合法赠品声明与数量 (优先从 NLP 精确提炼的赠品结构化清单对齐)
    extracted_freebies: Dict[str, int] = {}
    mentioned_freebie_names = []
    nlp_freebie_items = nlp_res.get("freebie_items", [])

    if freebie_type in ["single", "multiple"]:
        for fb in cat_info["allowed_freebies"]:
            names_to_check = [fb["name"]] + fb.get("alias", [])
            matched_qty = None
            
            # 先从 NLP 提炼的 freebie_items 中精确匹配
            for nlp_fb in nlp_freebie_items:
                nfb_name = nlp_fb.get("freebie_name", "")
                if any(alias in nfb_name or nfb_name in alias for alias in names_to_check):
                    matched_qty = nlp_fb.get("quantity", quantity)
                    break
            
            # 若 NLP 未提炼到，再用正则是做兜底
            if matched_qty is None:
                for alias in names_to_check:
                    pattern = rf'(?:送|附赠|赠送|和)?\s*([0-9]+)?\s*(?:个|把|只|张|套|盒|件)?\s*{re.escape(alias)}'
                    m = re.search(pattern, sales_input)
                    if m and alias in sales_input:
                        cnt = int(m.group(1)) if m.group(1) else 0
                        if cnt == 0 and freebie_type == "single":
                            cnt = quantity
                        matched_qty = cnt
                        break
            
            if matched_qty is not None:
                extracted_freebies[fb["name"]] = matched_qty
                mentioned_freebie_names.append(fb["name"])
    
    # 4. 判断是否需要弹窗提醒销售人员
    needs_modal = False
    reasons: List[str] = []
    
    # 铁律 1: 所有的电子商品都要有延保
    if not has_warranty:
        needs_modal = True
        reasons.append("MISSING_WARRANTY")
        
    # 铁律 2: 赠品规则
    if freebie_type == "single":
        # 单赠品：如果销售人员没有说要附加赠品，要出现弹窗提醒销售人员附加赠品并填写数量
        if not extracted_freebies or all(c == 0 for c in extracted_freebies.values()):
            needs_modal = True
            reasons.append("MISSING_SINGLE_FREEBIE")
    elif freebie_type == "multiple":
        # 多赠品：如果对应多种赠品就需要提醒销售人员去选择赠品类型，然后根据赠品类型去选择赠品的数量
        if not extracted_freebies:
            needs_modal = True
            reasons.append("CHOOSE_MULTIPLE_FREEBIES")
    elif freebie_type == "none":
        # 无赠品：直接下一步，就算销售人员说要附加赠品，直接无视
        pass
        
    return {
        "category_key": cat_info["category_key"],
        "category_name": cat_info["category_name"],
        "category_code": cat_info["category_code"],
        "freebie_type": freebie_type,
        "allowed_freebies": cat_info["allowed_freebies"],
        "quantity": quantity,
        "unit": unit,
        "product_term": product_term,
        "discount": discount,
        "clean_base_text": clean_base_text,
        "has_warranty": has_warranty,
        "warranty_years": warranty_years if has_warranty else 1, # 未声明时默认推荐1年
        "extracted_freebies": extracted_freebies,
        "structured_proposal_form": nlp_res,
        "needs_modal": needs_modal,
        "reasons": reasons
    }

def filter_and_calc_freebies(
    freebie_items: List[Any], 
    product_name: str, 
    order_quantity: int = 1
) -> tuple[float, List[dict]]:
    """
    根据标的商品所属权威品类，清洗并过滤非法赠品，计算合法专属赠品的成本清单。
    
    业务铁律：
    1. 散件/企业IT（无赠品品类）：任何赠品直接无视清零；
    2. 单赠品/多赠品品类：只有命中当前品类 allowed_freebies 及其别名（alias）的赠品才被认可；
    3. 非本品类赠品（如显卡送防爆钢化膜/手机壳）：直接丢弃无视，视为销售人员记错，绝不产生赠品成本；
    4. 容错解析：对大模型可能输出的 JSON 字符串或残缺符号做安全拆解，绝不显示 ': 1,' 等畸形名称。
    """
    import json
    
    cat_rule = detect_category_rule(product_name)
    freebie_type = cat_rule.get("freebie_type", "none")
    allowed_freebies = cat_rule.get("allowed_freebies", [])
    
    if freebie_type == "none" or not allowed_freebies:
        if freebie_items:
            print(f"[Freebie Rules] ⚠️ 拦截非法赠品诉求：标的商品属于【{cat_rule['category_name']}】，严格无赠品，销售提报赠品 {freebie_items} 视为记错，已直接无视清零！")
        return 0.0, []
        
    total_cost = 0.0
    details = []
    
    for raw_item in freebie_items:
        if not raw_item:
            continue
            
        item_text = str(raw_item).strip()
        item_qty = 0
        pure_name = ""
        
        # 1. 尝试解析 JSON 格式
        if "{" in item_text and "}" in item_text:
            try:
                normalized_json = item_text.replace("'", '"')
                m_json = re.search(r'\{[^{}]*\}', normalized_json)
                if m_json:
                    j_obj = json.loads(m_json.group(0))
                    if isinstance(j_obj, dict):
                        pure_name = str(j_obj.get("name", "")).strip()
                        item_qty = int(j_obj.get("quantity", 0))
            except Exception:
                pass
                
        # 2. 如果不是标准 JSON 或未解析成功，按纯文本正则提取
        if not pure_name:
            cleaned_text = re.sub(r'[{}\[\]"\'\\]', '', item_text).strip()
            m_qty = re.search(r'(\d+)', cleaned_text)
            if m_qty:
                item_qty = int(m_qty.group(1))
            pure_name = re.sub(r'^\d+\s*(?:个|把|只|张|套|盒|副)?', '', cleaned_text).strip()
            pure_name = re.sub(r'^(?:送|附赠|赠送|和)?\s*', '', pure_name).strip()
            pure_name = re.sub(r'^name\s*:\s*', '', pure_name, flags=re.IGNORECASE).strip()
            
        if not pure_name:
            continue
            
        if item_qty <= 0:
            item_qty = order_quantity if order_quantity > 0 else 1
            
        # 3. 品类专属白名单校验
        matched_cfg = None
        for cfg in allowed_freebies:
            all_names = [cfg["name"].lower()] + [a.lower() for a in cfg.get("alias", [])]
            if any(alias in pure_name.lower() or pure_name.lower() in alias for alias in all_names if len(alias) >= 2):
                matched_cfg = cfg
                break
                
        # 排他性互斥防线（防止“防爆钢化膜”被当作显卡或耳机的通用“膜/套”误匹配）
        if matched_cfg:
            if cat_rule["category_key"] == "GPU" and any(k in pure_name for k in ["膜", "壳", "套", "充", "手机", "键盘", "鼠标", "电脑包"]):
                if "支架" not in pure_name:
                    matched_cfg = None
            elif cat_rule["category_key"] == "EARPHONE" and any(k in pure_name for k in ["膜", "壳", "充", "支架", "键盘", "鼠标", "电脑包"]):
                if "套" not in pure_name:
                    matched_cfg = None
                    
        if not matched_cfg:
            print(f"[Freebie Rules] ⚠️ 拦截不属于该商品的非法赠品: '{raw_item}' (识别名: '{pure_name}') 不属于【{cat_rule['category_name']}】允许的专属赠品矩阵，视为销售人员记错，已直接无视过滤！")
            continue
            
        # 4. 属于合法专属赠品，标准化记录与成本折算
        unit_cost = float(matched_cfg["unit_cost"])
        item_total = round(unit_cost * item_qty, 2)
        total_cost += item_total
        
        display_name = f"{item_qty}个{matched_cfg['name']}"
        details.append({
            "name": display_name,
            "quantity": item_qty,
            "unit_cost": unit_cost,
            "total_cost": item_total
        })
        
    return round(total_cost, 2), details

