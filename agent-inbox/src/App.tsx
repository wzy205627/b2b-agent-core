import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Send, Inbox, Clock, CheckCircle2, AlertTriangle, X, RefreshCw, 
  ShieldAlert, Sparkles, TrendingUp, TrendingDown, DollarSign, Gift, Package, 
  RotateCcw, ThumbsDown, ThumbsUp, AlertCircle, ShieldCheck, Search,
  Smartphone, Laptop, Calculator, Sliders, Info,
  Cpu, Headphones, HardDrive
} from 'lucide-react';

interface FreebieDetail {
  name: string;
  quantity: number;
  unit_cost: number;
  total_cost: number;
}

interface ReturnedTask {
  thread_id: string;
  order_id?: string;
  task_status: string;
  supervisor_instructions?: string;
  target_discount?: number;
  target_warranty_years?: number;
  target_quantity?: number;
  target_freebies?: { [name: string]: number };
  previous_input?: string;
  product_name?: string;
  opp_id?: string;
  quantity?: number;
  unit?: string;
  unit_price?: number;
  cost_price?: number;
  warranty_cost_per_year?: number;
  current_stock?: number;
  stock_status?: string;
  shortage_qty?: number;
  requested_discount?: number;
  true_margin?: number;
  warranty_years?: number;
  freebie_items?: string[];
  freebie_details?: FreebieDetail[];
  revision_count?: number;
  risk_reasons?: string[];
  created_at: string;
  interrupt_data?: any;
}

interface Task {
  thread_id: string;
  order_id?: string;
  created_at: string;
  task_status?: string;
  interrupt_data: {
    reason: string;
    risk_reasons?: string[];
    margin_risk_level?: string;
    approval_level?: string;
    requested_discount: number;
    opp_id: string;
    order_id?: string;
    created_at?: string;
    product_name?: string;
    quantity?: number;
    unit?: string;
    unit_price?: number;
    cost_price?: number;
    total_amount?: number;
    final_amount?: number;
    bom_total_cost?: number;
    warranty_years?: number;
    warranty_cost_per_year?: number;
    warranty_total_cost?: number;
    freebie_items?: string[];
    freebie_details?: FreebieDetail[];
    freebie_total_cost?: number;
    combined_total_cost?: number;
    true_profit?: number;
    true_margin?: number;
    surface_profit?: number;
    surface_margin?: number;
    recovery_suggestions?: string[];
    current_stock?: number;
    stock_status?: string;
    shortage_qty?: number;
    task_status?: string;
    revision_count?: number;
    supervisor_instructions?: string;
    previous_input?: string;
  };
  current_values: {
    sales_input: string;
    discount: number;
    opportunity_id: string;
    product_name?: string;
    quantity?: number;
    unit?: string;
    total_amount?: number;
    final_amount?: number;
    true_margin?: number;
    true_profit?: number;
  };
}

interface AllowedFreebie {
  name: string;
  alias?: string[];
  unit_cost: number;
  unit?: string;
}

interface PreflightData {
  category_key: string;
  category_name: string;
  category_code: string;
  freebie_type: 'single' | 'multiple' | 'none';
  allowed_freebies: AllowedFreebie[];
  quantity: number;
  unit?: string;
  product_term?: string;
  discount?: number;
  clean_base_text?: string;
  has_warranty: boolean;
  warranty_years: number;
  extracted_freebies: { [name: string]: number };
  needs_modal: boolean;
  reasons: string[];
}

// 智能解析主管整改指令文本中的具体量化指标（折扣、延保、数量、赠品）
export const parseSupervisorInstructions = (
  instructions: string, 
  fallback?: {
    discount?: number;
    warranty_years?: number;
    quantity?: number;
    freebies?: { [name: string]: number };
  }
) => {
  let targetDisc = fallback?.discount;
  let targetWarranty = fallback?.warranty_years;
  let targetQty = fallback?.quantity;
  let targetFreebies: { [name: string]: number } = { ...(fallback?.freebies || {}) };

  if (instructions) {
    // 1. 折扣匹配 (支持: 申请折扣不得低于9折 / 不低于8.5折 / 调整至9折 / 打9折 / 至少9折 / 85% / 90%)
    const discMatch = instructions.match(/(?:不得低于|不低于|调整至|调整为|调至|上调至|建议|至少|要求|申请)?\s*(?:折扣|打)?\s*(?:不得低于|不低于|调整至|调整为|调至|上调至|建议|至少|要求)?\s*([0-9.]+)\s*折/);
    if (discMatch) {
      const d = parseFloat(discMatch[1]);
      if (!isNaN(d) && d > 0 && d <= 10) {
        targetDisc = d >= 1 ? d / 10 : d;
      }
    } else {
      const pctMatch = instructions.match(/(?:不得低于|不低于|调整至|调整为|调至|上调至|建议|至少|要求)?\s*(?:折扣)?\s*(?:不得低于|不低于|调整至|调整为|调至|上调至|建议|至少|要求)?\s*([0-9]{2,3})\s*%/);
      if (pctMatch) {
        const p = parseFloat(pctMatch[1]);
        if (!isNaN(p) && p >= 50 && p <= 100) {
          targetDisc = p / 100;
        }
      }
    }

    // 2. 延保匹配 (支持: 要求延保最多1年 / 最多1年 / 缩减至1年 / 取消延保 / 0年)
    if (/(?:取消|不送|无|0年)\s*(?:额外)?延保/.test(instructions)) {
      targetWarranty = 0;
    } else {
      const wMatch = instructions.match(/(?:延保|质保)(?:最多|缩减至|调整为|至多)?\s*([0-9]+)\s*年/) ||
                     instructions.match(/(?:最多|缩减至|调整为|至多)\s*([0-9]+)\s*年\s*(?:延保|质保)?/);
      if (wMatch) {
        targetWarranty = parseInt(wMatch[1]);
      }
    }

    // 3. 数量匹配 (支持: 现存仅10台 / 当前仅存10台 / 缩减至10台 / 调整本期提货量至10台 / 订购数量缩减至10台)
    const qMatch = instructions.match(/(?:现存仅|当前仅存|缩减至|调整本期提货量至|调整提货量至|订购数量.*?)\s*([0-9]+)\s*(?:台|盒|部|个)/);
    if (qMatch) {
      targetQty = parseInt(qMatch[1]);
    }

    // 4. 赠品匹配 (支持: 取消额外赠品 / 壳砍半至250个 / 支架缩减至25个 / 砍半至250个)
    if (/(?:取消|不送|无|清空)(?:额外)?赠品/.test(instructions)) {
      targetFreebies = {};
    } else {
      const fMatch = instructions.match(/([\u4e00-\u9fa5a-zA-Z0-9]+)?(?:砍半至|缩减至|至多|最多|保留|调整为)\s*([0-9]+)\s*个/);
      if (fMatch) {
        const keyword = fMatch[1];
        const count = parseInt(fMatch[2]);
        if (!isNaN(count)) {
          const keys = Object.keys(targetFreebies);
          let matched = false;
          for (const k of keys) {
            if (!keyword || k.includes(keyword) || (keyword && keyword.includes(k))) {
              targetFreebies[k] = count;
              matched = true;
            }
          }
          if (!matched && keys.length > 0) {
            targetFreebies[keys[0]] = count;
          }
        }
      }
    }
  }

  return {
    discount: targetDisc,
    warranty_years: targetWarranty,
    quantity: targetQty,
    freebies: targetFreebies
  };
};

// 格式化提单自然语言文本辅助函数
const extractTargetsFromInstructions = (instructions: string) => {
  let disc: number | undefined;
  let warranty: number | undefined;
  let qty: number | undefined;
  const freebies: { [name: string]: number } = {};

  if (!instructions) return { disc, warranty, qty, freebies };

  // 1. 折扣提取：支持 "不得低于9折", "不低于 9 折", "调整至9折", "建议9.0折", "9折", "8.8折", "8.5折" 等
  const discRegexes = [
    /(?:不低于|不得低于|调整至|建议|最低|上调至|至少)\s*([0-9.]+)\s*折/,
    /(?:折扣|折扣率).*?([0-9.]+)\s*折/,
    /([0-9.]+)\s*折/
  ];
  for (const reg of discRegexes) {
    const m = instructions.match(reg);
    if (m && m[1]) {
      const parsed = parseFloat(m[1]) / 10;
      if (!isNaN(parsed) && parsed >= 0.5 && parsed <= 1.0) {
        disc = parsed;
        break;
      }
    }
  }

  // 2. 延保提取：例如 "延保最多1年", "缩减至1年", "附赠1年延保", "延保调整为0年"
  const warrantyRegexes = [
    /(?:延保|质保).*?(?:最多|缩减至|调整为|不超过|至多)?\s*([0-9]+)\s*年/,
    /(?:最多|缩减至|不超过|至多)\s*([0-9]+)\s*年/
  ];
  for (const reg of warrantyRegexes) {
    const m = instructions.match(reg);
    if (m && m[1]) {
      const parsed = parseInt(m[1], 10);
      if (!isNaN(parsed) && parsed >= 0 && parsed <= 5) {
        warranty = parsed;
        break;
      }
    }
  }

  // 3. 订购数量提取：例如 "缩减至10台", "订购数量缩减至10台", "仅存10台"
  const qtyRegexes = [
    /(?:缩减至|调整至|订购数量.*?)\s*([0-9]+)\s*(?:台|盒|个|件)/,
    /仅存\s*([0-9]+)\s*(?:台|盒|个|件)/
  ];
  for (const reg of qtyRegexes) {
    const m = instructions.match(reg);
    if (m && m[1]) {
      const parsed = parseInt(m[1], 10);
      if (!isNaN(parsed) && parsed > 0) {
        qty = parsed;
        break;
      }
    }
  }

  return { disc, warranty, qty, freebies };
};

const formatSalesProposalText = (
  qty: number, 
  disc: number, 
  warrantyYears: number, 
  freebieQtys: { [name: string]: number }, 
  productName: string, 
  unit: string = '台'
) => {
  const discStr = (disc * 10).toFixed(1);
  let text = `帮我下 ${qty} ${unit} ${productName}，申请打 ${discStr} 折`;
  if (warrantyYears > 0) {
    text += `，并送 ${warrantyYears} 年延保`;
  }
  const freebieParts: string[] = [];
  Object.entries(freebieQtys).forEach(([name, count]) => {
    if (count > 0) {
      freebieParts.push(`${count}个${name}`);
    }
  });
  if (freebieParts.length > 0) {
    text += `和 ${freebieParts.join('、')}`;
  }
  return text;
};

function App() {
  const [salesInput, setSalesInput] = useState('帮我下 500 台 远峰蓝苹果18，申请打 8.8 折，并送 2 年延保和 500 个保护壳');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{status: string, message: string} | null>(null);
  
  // 主管待办队列与销售驳回待修队列
  const [tasks, setTasks] = useState<Task[]>([]);
  const [returnedTasks, setReturnedTasks] = useState<ReturnedTask[]>([]);
  const isPolling = true;

  // 销售提单前置预检与弹窗状态 (Preflight Modal)
  const [preflightData, setPreflightData] = useState<PreflightData | null>(null);
  const [isPreflightModalOpen, setIsPreflightModalOpen] = useState(false);
  const [modalWarrantyYears, setModalWarrantyYears] = useState<number>(1);
  const [modalFreebieQtys, setModalFreebieQtys] = useState<{ [name: string]: number }>({});
  const [modalSelectedFreebies, setModalSelectedFreebies] = useState<{ [name: string]: boolean }>({});
  const [categoryFreebieRules, setCategoryFreebieRules] = useState<any>({});
  
  // 销售端处于驳回修改模式的状态与专属测算沙盒
  const [resubmitThreadId, setResubmitThreadId] = useState<string | null>(null);
  const [activeReturnedTask, setActiveReturnedTask] = useState<ReturnedTask | null>(null);
  const [salesSimDiscount, setSalesSimDiscount] = useState<number>(0.90);
  const [salesSimDiscountStr, setSalesSimDiscountStr] = useState<string>('0.9');
  const [salesSimWarrantyYears, setSalesSimWarrantyYears] = useState<number>(0);
  const [salesSimQuantity, setSalesSimQuantity] = useState<number>(1);
  const [salesSimQuantityStr, setSalesSimQuantityStr] = useState<string>('1');
  const [salesSimFreebies, setSalesSimFreebies] = useState<{ [name: string]: number }>({});
  
  // 销售提单流式推进状态 (SSE Stream State)
  const [streamProgressMsg, setStreamProgressMsg] = useState<string>('');
  
  // 兜底降级结构化提单表单状态 (Fallback Form State)
  const [isFallbackFormOpen, setIsFallbackFormOpen] = useState(false);
  const [fallbackReason, setFallbackReason] = useState<string>('');
  const [productList, setProductList] = useState<any[]>([]);
  const [fallbackSelectedSku, setFallbackSelectedSku] = useState<string>('');
  const [fallbackSearchQuery, setFallbackSearchQuery] = useState<string>('');
  const [isSkuDropdownOpen, setIsSkuDropdownOpen] = useState<boolean>(false);
  const [isSkuConfirmed, setIsSkuConfirmed] = useState<boolean>(false);
  const [fallbackQuantity, setFallbackQuantity] = useState<number>(50);
  const [fallbackDiscount, setFallbackDiscount] = useState<number>(0.88);
  const [fallbackWarranty, setFallbackWarranty] = useState<number>(1);
  const [fallbackFreebieName, setFallbackFreebieName] = useState<string>('');
  const [fallbackFreebieQty, setFallbackFreebieQty] = useState<number>(0);

  // 3C与企业级IT权威专属赠品矩阵识别函数
  const getProductFreebieRule = (prodName: string, catStr: string = '') => {
    const t = (prodName + ' ' + catStr).toLowerCase();

    // 1. 独立显卡 GPU
    if (['显卡', 'rtx', '5090', '5080', '7900', 'geforce', 'radeon'].some(k => t.includes(k))) {
      return {
        type: 'single' as const,
        categoryName: '独立显卡',
        defaultFreebie: 'ROG 铝合金 ARGB 发光重型显卡支架',
        allowedFreebies: ['ROG 铝合金 ARGB 发光重型显卡支架']
      };
    }
    // 2. 蓝牙无线耳机 EARPHONE
    if (['耳机', 'airpods', 'freebuds', '1000xm5', '降噪豆'].some(k => t.includes(k))) {
      return {
        type: 'single' as const,
        categoryName: '无线蓝牙耳机',
        defaultFreebie: '液体硅胶防摔保护套',
        allowedFreebies: ['液体硅胶防摔保护套']
      };
    }
    // 3. 智能平板 TABLET
    if (['ipad', '平板', 'pad'].some(k => t.includes(k))) {
      return {
        type: 'single' as const,
        categoryName: '智能平板',
        defaultFreebie: '磁吸双面保护套',
        allowedFreebies: ['磁吸双面保护套']
      };
    }
    // 4. 笔记本电脑 LAPTOP (多种专属赠品)
    if (['笔记本', 'thinkpad', '拯救者', 'macbook', '枪神', '游戏本', '商务本'].some(k => t.includes(k))) {
      return {
        type: 'multiple' as const,
        categoryName: '笔记本电脑',
        allowedFreebies: [
          '拯救者 K7 客制化机械键盘',
          '罗技 MX Master 3S / 电竞无线鼠标',
          '拯救者多功能防震双肩电脑包'
        ]
      };
    }
    // 5. DIY 核心硬件散件 (严禁赠品)
    if (['固态', '机械硬盘', '990 pro', 'exos', '硬盘', 'ssd', 'nvme', 'cpu', '处理器', 'intel', '酷睿', 'i7', 'i9', 'ultra 9', 'amd', '锐龙', '9950x', '散热', '水冷', '风冷', '主板', '电源'].some(k => t.includes(k))) {
      return {
        type: 'none' as const,
        categoryName: 'DIY核心硬件散件',
        allowedFreebies: []
      };
    }
    // 6. 企业级 IT 设备 (严禁赠品)
    if (['交换机', '服务器', 'catalyst', 'poweredge'].some(k => t.includes(k))) {
      return {
        type: 'none' as const,
        categoryName: '企业级IT设备',
        allowedFreebies: []
      };
    }
    // 7. 旗舰智能手机 PHONE (多种专属赠品)
    if (['手机', '苹果18', 'mate70', '小米15', 'iphone', 'pro max', '远峰蓝', '羽砂黑', '暗夜紫'].some(k => t.includes(k))) {
      return {
        type: 'multiple' as const,
        categoryName: '旗舰智能手机',
        allowedFreebies: [
          '芳纶纤维磁吸防摔保护壳',
          'AR高透防爆钢化保护膜',
          '倍思 140W 氮化镓超级快充套装'
        ]
      };
    }

    return {
      type: 'none' as const,
      categoryName: '常规物料',
      allowedFreebies: []
    };
  };

  // 选中某一款候选商品并联动专属赠品
  const handleSelectProduct = (prod: any) => {
    setFallbackSelectedSku(prod.opp_id);
    setFallbackSearchQuery(prod.product_name);
    setIsSkuConfirmed(true);
    setIsSkuDropdownOpen(false);

    // 动态根据主商品品类规则联动专属赠品
    const rule = getProductFreebieRule(prod.product_name, prod.category_lvl1 || prod.category || '');
    if (rule.type === 'single') {
      setFallbackFreebieName(rule.defaultFreebie || '');
      setFallbackFreebieQty(fallbackQuantity); // 单一赠品默认自动填入
    } else if (rule.type === 'multiple') {
      setFallbackFreebieName(''); // 多种赠品默认待选
      setFallbackFreebieQty(0);
    } else {
      // none: 无法填入赠品，默认空白
      setFallbackFreebieName('');
      setFallbackFreebieQty(0);
    }
  };

  // 输入框变动：置为未确认状态并展开下拉供选择
  const handleSkuInputChange = (val: string) => {
    setFallbackSearchQuery(val);
    setIsSkuConfirmed(false);
    setIsSkuDropdownOpen(true);
    setFallbackSelectedSku('');
    setFallbackFreebieName('');
    setFallbackFreebieQty(0);
  };

  // 失焦清空防呆机制：销售人员只能选择搜索到的商品，输入无关内容或仅输入关键词未点击选择时全部清空
  const handleSkuInputBlur = () => {
    const confirmedProd = productList.find(p => p.opp_id === fallbackSelectedSku);
    if (!isSkuConfirmed || !confirmedProd || fallbackSearchQuery.trim() !== confirmedProd.product_name) {
      setFallbackSearchQuery('');
      setFallbackSelectedSku('');
      setIsSkuConfirmed(false);
      setFallbackFreebieName('');
      setFallbackFreebieQty(0);
    }
    setIsSkuDropdownOpen(false);
  };

  // 过滤商品物料列表 (支持单字、多词、空格交集分词、跨词子序列全动态模糊搜索)
  const filteredProductList = productList.filter(p => {
    const rawQ = fallbackSearchQuery.trim();
    if (!rawQ) return true;

    const pName = (p.product_name || '').toLowerCase();
    const opp = (p.opp_id || '').toLowerCase();
    const cat = (p.category_lvl1 || p.category || '').toLowerCase();
    const targetText = `${opp} ${pName} ${cat}`;

    const qLower = rawQ.toLowerCase();

    // 1. 完整连续子串匹配 (例如输入 "苹果", "苹果18", "远峰蓝", "5090", "暗夜紫", "耳机")
    if (targetText.includes(qLower)) return true;

    // 2. 按空格、逗号等符号拆解的多关键词交集 (AND匹配)
    // 例如用户输入: "苹果 远峰蓝" 或 "苹果 18 远峰蓝" 或 "5090 显卡"
    const spaceTokens = qLower.split(/[\s,，、]+/).filter(Boolean);
    if (spaceTokens.length > 1) {
      const allTokensMatch = spaceTokens.every(token => targetText.includes(token));
      if (allTokensMatch) return true;
    }

    // 3. 连续中文词段跨越匹配 (如果用户未敲空格连续输入，例如 "苹果远峰蓝" 或 "联想Y9000P")
    if (spaceTokens.length === 1 && rawQ.length >= 3) {
      const escapeRegex = (s: string) => s.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
      const segs: string[] = [];
      const knownBrands = ['苹果', '华为', '联想', '华硕', '小米', '索尼', '英伟达', '三星', '希捷'];
      for (const b of knownBrands) {
        if (qLower.startsWith(b) && qLower.length > b.length) {
          segs.push(b, qLower.slice(b.length));
          break;
        }
      }
      if (segs.length > 1) {
        try {
          const pattern = new RegExp(segs.map(escapeRegex).join('.*'), 'i');
          if (pattern.test(targetText)) return true;
        } catch (e) {}
      }
    }

    return false;
  });

  // 打开兜底降级表单并从当前自然语言提单中自动提取初始搜索词与参数
  const openFallbackModal = (reason: string) => {
    setFallbackReason(reason);
    
    // 如果当前 productList 为空，立即向后端重新请求一次，确保 100% 具备商品数据
    if (productList.length === 0) {
      axios.get('/api/products')
        .then(res => {
          const prods = res.data.products || [];
          setProductList(prods);
          if (prods.length > 0) {
            setFallbackSelectedSku(prods[0].opp_id);
          }
        })
        .catch(err => console.error("Error reloading products:", err));
    }

    let initSearch = '';
    let initQty = 50;
    let initDisc = 0.88;
    let initWar = 1;
    let initFbQty = 0;

    if (salesInput.trim()) {
      const raw = salesInput.trim();
      const mQty = raw.match(/(\d+)\s*(?:台|盒|副|片|块|套|个|把|只|本|张)/);
      if (mQty) initQty = parseInt(mQty[1]);

      const mDisc = raw.match(/([0-9.]+)\s*折/);
      if (mDisc) initDisc = parseFloat(mDisc[1]) / 10.0;

      const mWar = raw.match(/(\d+)\s*年\s*(?:延保|质保|保修)/);
      if (mWar) initWar = parseInt(mWar[1]);

      const mFb = raw.match(/(\d+)\s*(?:个|把|只|张|套|盒|副|件)\s*[^，,。！!；;\n]+/);
      if (mFb) initFbQty = parseInt(mFb[1]);

      // 提取主商品词：从数量后开始，截取到下一个符号或让利词
      const startPos = mQty ? (raw.indexOf(mQty[0]) + mQty[0].length) : 0;
      const rem = raw.substring(startPos).trim();
      let prodTerm = rem.split(/[，,和加送附赠外加包包含申请打]/)[0].trim();
      if (!prodTerm || prodTerm.length < 2) {
        prodTerm = raw.replace(/^(帮我下|帮我定|我要买|采购|下单|下)\s*/, '').split(/[，,和加送附赠外加包包含申请打]/)[0].trim();
      }
      if (prodTerm) {
        initSearch = prodTerm;
      }
    }

    if (initSearch) {
      setFallbackSearchQuery(initSearch);
      const matched = productList.find(p => p.product_name.includes(initSearch) || initSearch.includes(p.product_name));
      if (matched) {
        setFallbackSelectedSku(matched.opp_id);
        setFallbackSearchQuery(matched.product_name);
        setIsSkuConfirmed(true);
        setIsSkuDropdownOpen(false);
        const rule = getProductFreebieRule(matched.product_name, matched.category_lvl1 || matched.category || '');
        if (rule.type === 'single') {
          setFallbackFreebieName(rule.defaultFreebie || '');
          setFallbackFreebieQty(initFbQty > 0 ? initFbQty : initQty);
        } else if (rule.type === 'multiple') {
          setFallbackFreebieName('');
          setFallbackFreebieQty(0);
        } else {
          setFallbackFreebieName('');
          setFallbackFreebieQty(0);
        }
      } else {
        setFallbackSelectedSku('');
        setIsSkuConfirmed(false);
        setIsSkuDropdownOpen(false);
        setFallbackFreebieName('');
        setFallbackFreebieQty(0);
      }
    } else {
      setFallbackSearchQuery('');
      setFallbackSelectedSku('');
      setIsSkuConfirmed(false);
      setIsSkuDropdownOpen(false);
      setFallbackFreebieName('');
      setFallbackFreebieQty(0);
    }

    setFallbackQuantity(initQty);
    setFallbackDiscount(initDisc);
    setFallbackWarranty(initWar);
    setIsFallbackFormOpen(true);
  };


  // 主管抽屉状态

  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [decisionTab, setDecisionTab] = useState<'approve' | 'reject'>('approve');
  const [approvedDiscount, setApprovedDiscount] = useState<number>(0.88);
  const [approvedDiscountStr, setApprovedDiscountStr] = useState<string>('0.88');
  const [comment, setComment] = useState('同意特批放行');
  const [rejectInstructions, setRejectInstructions] = useState('变相让利过多导致毛利率跌破红线！要求延保最多1年，壳砍半至250个，申请折扣不得低于9折！');
  const [isResuming, setIsResuming] = useState(false);

  // 主管交互式整改测算栏沙盒状态 (Revision Simulator)
  const [simDiscount, setSimDiscount] = useState<number>(0.88);
  const [simDiscountStr, setSimDiscountStr] = useState<string>('0.88');
  const [simQuantity, setSimQuantity] = useState<number>(1);
  const [simQuantityStr, setSimQuantityStr] = useState<string>('1');
  const [simWarrantyYears, setSimWarrantyYears] = useState<number>(0);
  const [simFreebieQtys, setSimFreebieQtys] = useState<{ [name: string]: number }>({});

  useEffect(() => {
    // 载入品类规则
    axios.get('/api/product-freebie-rules')
      .then(res => setCategoryFreebieRules(res.data.rules || {}))
      .catch(err => console.error("Error fetching rules:", err));

    // 载入商品物料清单 (供兜底结构化表单使用)
    axios.get('/api/products')
      .then(res => {
        const prods = res.data.products || [];
        setProductList(prods);
        if (prods.length > 0) {
          setFallbackSelectedSku(prods[0].opp_id);
        }
      })
      .catch(err => console.error("Error fetching products:", err));
  }, []);

  // 1. 自动轮询待办与驳回队列
  const fetchAllTasks = async () => {
    try {
      const [pendingRes, returnedRes] = await Promise.all([
        axios.get('/api/pending-tasks'),
        axios.get('/api/sales/returned-tasks')
      ]);
      setTasks(pendingRes.data.tasks || []);
      setReturnedTasks(returnedRes.data.tasks || []);
    } catch (err) {
      console.error("Error fetching tasks:", err);
    }
  };

  useEffect(() => {
    if (isPolling) {
      fetchAllTasks();
      const interval = setInterval(fetchAllTasks, 3000);
      return () => clearInterval(interval);
    }
  }, [isPolling]);

  // 执行最终提交提单 (升级为 SSE 流式输出 + 心跳保活 + 降级表单感知)
  const doActualSubmit = async (inputToSubmit: string) => {
    setIsSubmitting(true);
    setSubmitResult(null);
    setStreamProgressMsg('正在连接 AI 智能体服务...');

    try {
      const response = await fetch('/api/submit-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sales_input: inputToSubmit })
      });

      if (!response.body) {
        throw new Error('ReadableStream not supported');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const block of lines) {
          const trimmed = block.trim();
          if (trimmed.startsWith('data:')) {
            try {
              const data = JSON.parse(trimmed.slice(5).trim());

              if (data.event === 'STARTED') {
                setStreamProgressMsg(data.message);
              } else if (data.event === 'HEARTBEAT') {
                // 每 2 秒心跳保活与推进展示
                setStreamProgressMsg(`⏳ ${data.message} (耗时 ${data.step * 2}s)`);
              } else if (data.event === 'CIRCUIT_OPEN') {
                // 断路器熔断：触发业务体验层无缝降级表单
                setStreamProgressMsg('');
                setIsSubmitting(false);
                openFallbackModal(data.message || 'AI 算力暂时拥塞，已触发系统熔断防护！');
                return;
              } else if (data.event === 'TIMEOUT') {
                setSubmitResult({
                  status: 'TIMEOUT',
                  message: data.message || 'AI 运算超时，已为您切换至标准结构化提单模式'
                });
                setStreamProgressMsg('');
                openFallbackModal(data.message || 'AI 状态机运算超时，已切换至标准提单表单');
              } else if (data.event === 'INTERRUPT') {
                setSubmitResult({
                  status: data.status,
                  message: data.message || '已命中风控红线，已挂起等待主管审批'
                });
                setStreamProgressMsg('');
                fetchAllTasks();
              } else if (data.event === 'NOT_FOUND') {
                setSubmitResult({
                  status: 'NOT_FOUND',
                  message: data.message || '商品库中未能匹配到相关商品'
                });
                setStreamProgressMsg('');
                openFallbackModal('AI 无法准确解析该口语提单中的商品，请使用标准提单表单录入！');
              } else if (data.event === 'COMPLETED') {
                setSubmitResult({
                  status: data.status,
                  message: data.message || '提单已自动通过放行'
                });
                setStreamProgressMsg('');
                fetchAllTasks();
              } else if (data.event === 'ERROR') {
                setSubmitResult({
                  status: 'ERROR',
                  message: data.message
                });
                setStreamProgressMsg('');
                if (data.fallback_required) {
                  openFallbackModal(data.message || '执行异常，请使用标准表单录入');
                }
              }
            } catch (jsonErr) {
              console.error("Parse stream block error:", jsonErr);
            }
          }
        }
      }
    } catch (err: any) {
      console.error("SSE stream error:", err);
      setSubmitResult({ status: 'ERROR', message: '连接中断或服务异常，请使用标准表单录入' });
      openFallbackModal('网络连接超时或服务波动，请直接通过标准表单录入');
    } finally {
      setIsSubmitting(false);
      setStreamProgressMsg('');
    }
  };


  // 2. 销售发起新提单或重新提交驳回修改
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!salesInput.trim()) return;
    
    // 如果是重新提交被驳回的提单
    if (resubmitThreadId) {
      setIsSubmitting(true);
      setSubmitResult(null);
      try {
        const res = await axios.post(`/api/sales/resubmit/${resubmitThreadId}`, {
          revised_input: salesInput
        });
        setSubmitResult({
          status: res.data.status,
          message: res.data.message || '修改方案已重新提交至主管端二次审批'
        });
        setResubmitThreadId(null);
        setActiveReturnedTask(null);
        fetchAllTasks();
      } catch (err) {
        setSubmitResult({ status: 'ERROR', message: '提交失败，请检查网络或后端服务状态' });
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // 全新提单：先进行 Preflight 规则预检！
    setIsSubmitting(true);
    setSubmitResult(null);
    try {
      const checkRes = await axios.post('/api/preflight-check', { sales_input: salesInput });
      const pData: PreflightData = checkRes.data;
      
      if (pData && pData.needs_modal) {
        setPreflightData(pData);
        // 初始化延保
        setModalWarrantyYears(pData.has_warranty ? (pData.warranty_years || 1) : 1);
        // 初始化赠品数量与选中状态
        const initialQtys: { [name: string]: number } = {};
        const initialSelected: { [name: string]: boolean } = {};
        
        pData.allowed_freebies.forEach(f => {
          const extracted = pData.extracted_freebies ? pData.extracted_freebies[f.name] : undefined;
          if (extracted !== undefined && extracted > 0) {
            initialQtys[f.name] = extracted;
            initialSelected[f.name] = true;
          } else if (pData.freebie_type === 'single') {
            // 单赠品：无论销售提没提，默认 1:1 或 1，且默认勾选
            initialQtys[f.name] = pData.quantity > 0 ? pData.quantity : 1;
            initialSelected[f.name] = true;
          } else {
            // 多赠品：默认填入 1:1，但默认未勾选，提醒销售按需勾选类型与数量
            initialQtys[f.name] = pData.quantity > 0 ? pData.quantity : 1;
            initialSelected[f.name] = false;
          }
        });
        setModalFreebieQtys(initialQtys);
        setModalSelectedFreebies(initialSelected);
        setIsPreflightModalOpen(true);
        setIsSubmitting(false);
        return;
      }
      
      // 若已完整合规，直接提交
      await doActualSubmit(salesInput);
    } catch (err) {
      console.error("Preflight check failed, fallback to direct submit:", err);
      await doActualSubmit(salesInput);
    }
  };

  // 确认 Preflight 弹窗配置并组装提单提交（彻底清洗剥离无关/错误赠品，仅附加合规专属赠品与延保）
  const confirmPreflightAndSubmit = async () => {
    if (!preflightData) return;
    
    let rawText = salesInput.trim();
    
    // 1. 确定最终延保年数
    let finalWarrantyYears = modalWarrantyYears;
    const warMatch = rawText.match(/(?:送|赠|加|附带|包含)\s*([0-9]+)\s*年\s*延保/);
    if (warMatch && modalWarrantyYears <= 0) {
      finalWarrantyYears = parseInt(warMatch[1]);
    }
    
    // 2. 提取纯净采购主需求（数量 + 单位 + 主商品名称 + 申请折扣）
    // 彻底阻断并剥离任何夹杂在主商品后（如 "和 50 个防丢绳"）或末尾（如 "和 500 个保护壳"）的无关赠品
    let cleanBaseText = preflightData.clean_base_text;
    if (!cleanBaseText) {
      const mQty = rawText.match(/(\d+)\s*(台|盒|副|片|块|套|个|把|只|本|张)/);
      const qty = mQty ? mQty[1] : (preflightData.quantity || '1');
      const unit = mQty ? mQty[2] : (preflightData.unit || '台');
      
      const mDisc = rawText.match(/([0-9.]+)\s*折/);
      const discStr = mDisc ? `，申请打 ${mDisc[1]} 折` : '';
      
      // 提取纯净主商品词：从数量后开始，截取到下一个非主商品连接标记（和/加/外加/送/附赠/，/申请/打折）
      const startPos = mQty ? (rawText.indexOf(mQty[0]) + mQty[0].length) : 0;
      const rem = rawText.substring(startPos).trim();
      let prodName = rem.split(/[，,和加送附赠外加包包含申请打]/)[0].trim();
      if (!prodName || prodName.length < 2) {
        prodName = preflightData.product_term || preflightData.category_name || '商品';
      }
      cleanBaseText = `帮我下 ${qty} ${unit} ${prodName}${discStr}`;
    }
    
    // 3. 组装规范延保条款
    let warrantyPart = '';
    if (finalWarrantyYears > 0) {
      warrantyPart = `，并送 ${finalWarrantyYears} 年延保`;
    }
    
    // 4. 组装合规专属赠品条款（严格只追加在弹窗中选中并确认的专属赠品）
    const validFreebieParts: string[] = [];
    if (preflightData.freebie_type !== 'none') {
      preflightData.allowed_freebies.forEach(f => {
        if (modalSelectedFreebies[f.name] && (modalFreebieQtys[f.name] || 0) > 0) {
          validFreebieParts.push(`${modalFreebieQtys[f.name]}个${f.name}`);
        }
      });
    }
    
    let freebieClause = '';
    if (validFreebieParts.length > 0) {
      if (warrantyPart) {
        freebieClause = `和 ${validFreebieParts.join('、')}`;
      } else {
        freebieClause = `，送 ${validFreebieParts.join('、')}`;
      }
    }
    
    const finalSalesInput = cleanBaseText + warrantyPart + freebieClause;
    
    setSalesInput(finalSalesInput);
    setIsPreflightModalOpen(false);
    setPreflightData(null);
    
    await doActualSubmit(finalSalesInput);
  };

  // 3. 销售端一键载入被驳回的提单以供修改
  const handleLoadRevision = (task: ReturnedTask) => {
    setActiveReturnedTask(task);
    setResubmitThreadId(task.thread_id);

    // 智能提取主管整改目标（指令文本智能解析与结构化指标融合）
    const instTargets = extractTargetsFromInstructions(task.supervisor_instructions || '');
    
    // 折扣优先级：
    // 若指示文本中有明确整改要求（例如"不得低于9折"提取出 0.9），
    // 且当前结构化 target_discount 为空，或等于原单旧折扣 requested_discount，或文本要求比结构化字段更严格，
    // 则坚决优先采纳指示文本中的要求！
    let finalDisc = task.target_discount;
    if (instTargets.disc !== undefined) {
      if (
        finalDisc === undefined ||
        (task.requested_discount && Math.abs(finalDisc - task.requested_discount) < 0.001) ||
        instTargets.disc > finalDisc
      ) {
        finalDisc = instTargets.disc;
      }
    }
    if (finalDisc === undefined) {
      finalDisc = task.requested_discount ?? 0.90;
    }

    // 延保优先级：
    let finalWarranty = task.target_warranty_years;
    if (instTargets.warranty !== undefined) {
      finalWarranty = instTargets.warranty;
    } else if (finalWarranty === undefined) {
      finalWarranty = task.warranty_years !== undefined ? Math.min(1, task.warranty_years) : 1;
    }

    // 订购量优先级：
    let finalQty = task.target_quantity ?? task.quantity ?? 1;
    if (instTargets.qty !== undefined && instTargets.qty < finalQty) {
      finalQty = instTargets.qty;
    }

    let targetFreebies = task.target_freebies ?? {};

    setSalesSimDiscount(finalDisc);
    setSalesSimDiscountStr(finalDisc.toString());
    setSalesSimWarrantyYears(finalWarranty);
    setSalesSimQuantity(finalQty);
    setSalesSimQuantityStr(finalQty.toString());
    setSalesSimFreebies(targetFreebies);

    // 自动根据主管要求生成更新后的提单申请语句
    const updatedText = formatSalesProposalText(
      finalQty, 
      finalDisc, 
      finalWarranty, 
      targetFreebies, 
      task.product_name || '商品', 
      task.unit || '台'
    );
    setSalesInput(updatedText);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // 销售端一键采纳主管全部具体整改指标
  const adoptSupervisorTargets = () => {
    if (!activeReturnedTask) return;
    
    // 从主管整改文本中提取整改意图
    const instTargets = extractTargetsFromInstructions(activeReturnedTask.supervisor_instructions || '');

    // 折扣优先级：确保精准采纳主管要求（如 9 折）
    let finalDisc = activeReturnedTask.target_discount;
    if (instTargets.disc !== undefined) {
      if (
        finalDisc === undefined ||
        (activeReturnedTask.requested_discount && Math.abs(finalDisc - activeReturnedTask.requested_discount) < 0.001) ||
        instTargets.disc > finalDisc
      ) {
        finalDisc = instTargets.disc;
      }
    }
    if (finalDisc === undefined) {
      finalDisc = 0.90;
    }

    // 延保优先级：
    let finalWarranty = activeReturnedTask.target_warranty_years;
    if (instTargets.warranty !== undefined) {
      finalWarranty = instTargets.warranty;
    } else if (finalWarranty === undefined) {
      finalWarranty = 1;
    }

    // 订购量优先级：
    let finalQty = activeReturnedTask.target_quantity ?? activeReturnedTask.quantity ?? 1;
    if (instTargets.qty !== undefined && instTargets.qty < finalQty) {
      finalQty = instTargets.qty;
    }

    let targetFreebies = activeReturnedTask.target_freebies ?? {};

    // 响应式更新销售微调沙盒
    setSalesSimDiscount(finalDisc);
    setSalesSimDiscountStr(finalDisc.toString());
    setSalesSimWarrantyYears(finalWarranty);
    setSalesSimQuantity(finalQty);
    setSalesSimQuantityStr(finalQty.toString());
    setSalesSimFreebies(targetFreebies);

    // 同步生成自然语言申请文本并填入输入框
    const text = formatSalesProposalText(
      finalQty, 
      finalDisc, 
      finalWarranty, 
      targetFreebies, 
      activeReturnedTask.product_name || '商品', 
      activeReturnedTask.unit || '台'
    );
    setSalesInput(text);
  };

  // 销售端将测算沙盒方案同步更新至提单文本
  const syncSalesSimToText = () => {
    if (!activeReturnedTask) return;
    const text = formatSalesProposalText(
      salesSimQuantity, 
      salesSimDiscount, 
      salesSimWarrantyYears, 
      salesSimFreebies, 
      activeReturnedTask.product_name || '商品', 
      activeReturnedTask.unit || '台'
    );
    setSalesInput(text);
  };

  // 获取当前任务可供主管测算的赠品列表 (即使原单未带赠品也可按品类自动加载专属赠品)
  const getDrawerFreebieList = (task: Task | null) => {
    if (!task) return [];
    const data = task.interrupt_data;
    if (data.freebie_details && data.freebie_details.length > 0) {
      return data.freebie_details;
    }
    const prodName = data.product_name || '';
    let matchedRule: any = null;
    if (/显卡|GPU|RTX/i.test(prodName)) matchedRule = categoryFreebieRules['GPU'];
    else if (/手机|iPhone|苹果18|Mate/i.test(prodName)) matchedRule = categoryFreebieRules['PHONE'];
    else if (/耳机|AirPods|FreeBuds/i.test(prodName)) matchedRule = categoryFreebieRules['EARPHONE'];
    else if (/笔记本|电脑|拯救者|ThinkPad/i.test(prodName)) matchedRule = categoryFreebieRules['LAPTOP'];
    else if (/平板|iPad|MatePad/i.test(prodName)) matchedRule = categoryFreebieRules['TABLET'];

    if (matchedRule && matchedRule.freebie_type !== 'none' && matchedRule.allowed_freebies) {
      return matchedRule.allowed_freebies.map((f: any) => ({
        name: f.name,
        quantity: 0,
        unit_cost: f.unit_cost,
        total_cost: 0
      }));
    }
    return [];
  };

  const cancelRevision = () => {
    setResubmitThreadId(null);
    setActiveReturnedTask(null);
    setSalesInput('帮我下 500 台 远峰蓝苹果18，申请打 8.8 折，并送 2 年延保和 500 个保护壳');
  };

  // 4. 打开抽屉并初始化主管整改测算沙盒
  const openDrawer = (task: Task) => {
    setSelectedTask(task);
    const data = task.interrupt_data;
    const initialDiscount = data.requested_discount || 0.88;
    setApprovedDiscount(initialDiscount);
    setApprovedDiscountStr(initialDiscount.toString());
    setDecisionTab('approve');

    // 初始化交互式整改测算沙盒
    setSimDiscount(initialDiscount);
    setSimDiscountStr(initialDiscount.toString());
    const initialQty = data.quantity || 1;
    setSimQuantity(initialQty);
    setSimQuantityStr(initialQty.toString());
    setSimWarrantyYears(data.warranty_years || 0);
    
    // 初始化赠品调控列表
    const drawerFreebies = getDrawerFreebieList(task);
    const initialFreebies: { [name: string]: number } = {};
    drawerFreebies.forEach((item: any) => {
      initialFreebies[item.name] = item.quantity;
    });
    setSimFreebieQtys(initialFreebies);

    if (data.margin_risk_level === 'CRITICAL_LOSS' || (data.true_profit !== undefined && data.true_profit < 0)) {
      setComment('CFO 批示：严禁击穿 BOM 底线倒贴！必须上调折扣或砍掉赠品与延保');
      setRejectInstructions('🚨 严重击穿 BOM 底线成本！单台倒贴亏损，要求折扣不低于 8.5 折并取消额外赠品延保，重新提单！');
      setSimDiscount(0.85);
      setSimDiscountStr('0.85');
      setSimWarrantyYears(0);
    } else if (data.margin_risk_level === 'VP_SPECIAL' || (data.true_margin !== undefined && data.true_margin < 15)) {
      setComment('VP 特批放行：属于战略竞争客户，同意微利签约，延保与配件由区域市场营销预算全额冲抵');
      setRejectInstructions('变相让利过多导致综合毛利率跌破红线！要求延保最多1年，壳砍半至250个，申请折扣不得低于9折！');
      setSimDiscount(0.90);
      setSimDiscountStr('0.9');
      setSimWarrantyYears(1);
    } else if (data.stock_status === 'SHORTAGE') {
      setComment('总监批示：现货部分先发，缺口申请工厂加急调拨排产');
      setRejectInstructions(`现货库存短缺！当前仅存 ${data.current_stock || 0}${data.unit || '台'}，请调整本期提货量或协调分批交付`);
      if (data.current_stock && data.current_stock > 0) {
        setSimQuantity(data.current_stock);
        setSimQuantityStr(data.current_stock.toString());
      }
    } else {
      setComment('总监审批放行：真实综合利润与让利核算达标，同意放行');
      setRejectInstructions('综合利润略低，建议适当减少赠品承诺后重新提交');
    }
  };

  // 5. 主管交互式整改测算联动计算逻辑
  const simData = selectedTask?.interrupt_data;
  const originalSimQty = simData?.quantity || 1;
  const currentStock = simData?.current_stock || 0;
  const isStockShortage = currentStock < originalSimQty;
  const simUnitPrice = simData?.unit_price || 0;
  const simCostPrice = simData?.cost_price || 0;
  const simWarrantyRate = simData?.warranty_cost_per_year || 0;

  // 5.1 联动实收与成本 (基于 simQuantity 动态重算)
  const simContractRevenue = Math.round(simUnitPrice * simDiscount * simQuantity);
  const simBomCost = Math.round(simCostPrice * simQuantity);
  const simWarrantyCost = Math.round(simWarrantyRate * simWarrantyYears * simQuantity);
  
  const drawerFreebieList = getDrawerFreebieList(selectedTask);
  let simFreebieCost = 0;
  if (drawerFreebieList.length > 0) {
    simFreebieCost = drawerFreebieList.reduce((sum: number, item: any) => {
      const q = simFreebieQtys[item.name] !== undefined ? simFreebieQtys[item.name] : item.quantity;
      return sum + Math.round(item.unit_cost * q);
    }, 0);
  }
  const simCombinedCost = simBomCost + simWarrantyCost + simFreebieCost;
  const simTrueProfit = simContractRevenue - simCombinedCost;
  const simTrueMargin = simContractRevenue > 0 ? ((simTrueProfit / simContractRevenue) * 100) : 0;

  // 5.6 联动试算风险评级
  let simRiskLevel = 'NORMAL';
  let simApprovalLevel = '系统自动放行';
  if (simTrueProfit < 0 || (simUnitPrice * simDiscount < simCostPrice)) {
    simRiskLevel = 'CRITICAL_LOSS';
    simApprovalLevel = 'CFO 一票否决级特批 (极高风险)';
  } else if (simTrueMargin < 15.0) {
    simRiskLevel = 'VP_SPECIAL';
    simApprovalLevel = '业务副总裁 (VP) 特批 (偏高风险)';
  } else if (simTrueMargin < 25.0) {
    simRiskLevel = 'DIRECTOR_REVIEW';
    simApprovalLevel = '部门总监常规审批 (中度风险)';
  } else {
    simRiskLevel = 'NORMAL';
    simApprovalLevel = '达标合规 (正常放行)';
  }

  // 6. 将整改测算沙盒中的参数自动生成自然语言整改指示
  const applySimulationToInstructions = () => {
    if (!selectedTask) return;
    const data = selectedTask.interrupt_data;
    
    const freebieTexts: string[] = [];
    if (data.freebie_details && data.freebie_details.length > 0) {
      data.freebie_details.forEach(item => {
        const q = simFreebieQtys[item.name] !== undefined ? simFreebieQtys[item.name] : item.quantity;
        freebieTexts.push(`${item.name} 调整为 ${q} 个`);
      });
    }
    const freebieDesc = freebieTexts.length > 0 ? freebieTexts.join('，') : '取消额外赠品配件';

    let itemIdx = 1;
    let qtyClause = '';
    if (simQuantity < originalSimQty) {
      qtyClause = `${itemIdx}. 【订购数量】：因现存库存不足（现货仅存 ${currentStock} 台，缺口 ${originalSimQty - currentStock} 台），建议将订购数量缩减至 ${simQuantity} 台（缺口消除）；\n`;
      itemIdx++;
    }

    const instructionText = `【主管整改指示】：原提单方案让利过大侵蚀公司利润，经测算请按以下具体指标整改后重新提单：
${qtyClause}${itemIdx++}. 【申请折扣】：调整至不低于 ${(simDiscount * 10).toFixed(1)} 折（折后合同实收 ¥${simContractRevenue.toLocaleString()}）；
${itemIdx++}. 【附赠延保】：缩减至最多 ${simWarrantyYears} 年（折合成本 ¥${simWarrantyCost.toLocaleString()}）；
${itemIdx++}. 【赠品配件】：${freebieDesc}（折合成本 ¥${simFreebieCost.toLocaleString()}）；
【整改预期】：综合履约成本由 ¥${(data.combined_total_cost || 0).toLocaleString()} 降至 ¥${simCombinedCost.toLocaleString()}，真实净毛利由 ¥${(data.true_profit || 0).toLocaleString()} 回升至 ¥${simTrueProfit.toLocaleString()}，真实毛利率由 ${(data.true_margin || 0).toFixed(2)}% 提升至 ${simTrueMargin.toFixed(2)}%（达标【${simApprovalLevel}】要求）！请确认现货库存满足后立即重新提交！`;

    setRejectInstructions(instructionText);
  };

  // 7. 主管审批决策 (同意放行 OR 驳回修改)
  const handleSupervisorDecision = async () => {
    if (!selectedTask) return;
    setIsResuming(true);

    try {
      if (decisionTab === 'reject') {
        // 智能保障：如果 instructions 中有具体整改折扣要求（如 9折），而沙盒没变动还是原单旧折扣，优先采纳指示要求的严格指标
        const extracted = extractTargetsFromInstructions(rejectInstructions);
        let finalTargetDisc = simDiscount;
        if (extracted.disc !== undefined) {
          if (
            (selectedTask.interrupt_data.requested_discount && Math.abs(finalTargetDisc - selectedTask.interrupt_data.requested_discount) < 0.001) ||
            extracted.disc > finalTargetDisc
          ) {
            finalTargetDisc = extracted.disc;
          }
        }
        let finalTargetWarranty = simWarrantyYears;
        if (extracted.warranty !== undefined) {
          finalTargetWarranty = extracted.warranty;
        }
        let finalTargetQty = simQuantity;
        if (extracted.qty !== undefined && extracted.qty < finalTargetQty) {
          finalTargetQty = extracted.qty;
        }

        // 驳回并同步结构化指标
        await axios.post(`/api/supervisor/decision/${selectedTask.thread_id}`, {
          action: 'reject',
          instructions: rejectInstructions,
          comment: `主管驳回：${rejectInstructions}`,
          target_discount: finalTargetDisc,
          target_warranty_years: finalTargetWarranty,
          target_quantity: finalTargetQty,
          target_freebies: simFreebieQtys
        });
      } else {
        // 同意
        await axios.post(`/api/supervisor/decision/${selectedTask.thread_id}`, {
          action: 'approve',
          approved_discount: Number(approvedDiscount),
          comment: comment
        });
      }
      setSelectedTask(null);
      fetchAllTasks();
    } catch (err: any) {
      const errorDetail = err?.response?.data?.detail;
      if (errorDetail) {
        alert(`审批提示：${errorDetail}`);
      } else {
        alert("审批决策提交失败！该任务可能已在其他终端处理或后端连接异常。");
      }
      setSelectedTask(null);
      fetchAllTasks();
    } finally {
      setIsResuming(false);
    }
  };

  // 销售端整改沙盒实时财务核算
  const salesTask = activeReturnedTask;
  const salesUnitPrice = salesTask?.unit_price || (salesTask?.interrupt_data?.unit_price) || 0;
  const salesCostPrice = salesTask?.cost_price || (salesTask?.interrupt_data?.cost_price) || 0;
  const salesWarrantyRate = salesTask?.warranty_cost_per_year || (salesTask?.interrupt_data?.warranty_cost_per_year) || 0;
  const salesCurrentStock = salesTask?.current_stock || (salesTask?.interrupt_data?.current_stock) || 0;
  const salesOriginalQty = salesTask?.quantity || 1;
  const salesHasShortage = salesCurrentStock < salesOriginalQty;

  const salesRevenue = Math.round(salesUnitPrice * salesSimDiscount * salesSimQuantity);
  const salesBomCost = Math.round(salesCostPrice * salesSimQuantity);
  const salesWarrantyCost = Math.round(salesWarrantyRate * salesSimWarrantyYears * salesSimQuantity);
  let salesFreebieCost = 0;
  if (salesTask?.freebie_details && salesTask.freebie_details.length > 0) {
    salesFreebieCost = salesTask.freebie_details.reduce((sum, item) => {
      const q = salesSimFreebies[item.name] !== undefined ? salesSimFreebies[item.name] : 0;
      return sum + Math.round(item.unit_cost * q);
    }, 0);
  }
  const salesCombinedCost = salesBomCost + salesWarrantyCost + salesFreebieCost;
  const salesTrueProfit = salesRevenue - salesCombinedCost;
  const salesTrueMargin = salesRevenue > 0 ? ((salesTrueProfit / salesRevenue) * 100) : 0;

  const applyAiSuggestionToReject = () => {
    if (selectedTask?.interrupt_data.recovery_suggestions?.length) {
      const combined = selectedTask.interrupt_data.recovery_suggestions.join('；');
      setRejectInstructions(`根据风控系统建议调整：${combined}，请修改提单方案后重新提交！`);
    }
  };

  const applyPreset = (text: string) => {
    setResubmitThreadId(null);
    setActiveReturnedTask(null);
    setSalesInput(text);
  };

  return (
    <div className="app-container">
      {/* ================= 左侧：销售模拟终端 ================= */}
      <aside className="left-panel">
        <div>
          <h1><Send size={24} color="var(--primary)" /> 销售提单终端</h1>
          <p className="subtitle">Sales Terminal | 3C电子与企业级IT防资损平台</p>
        </div>

        {/* 快捷测试预置场景 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.5rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>🎯 3C全品类与专属赠品测试用例:</span>
          <button 
            type="button" 
            className="btn" 
            style={{ fontSize: '0.75rem', padding: '0.45rem 0.65rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#F87171', border: '1px solid rgba(239, 68, 68, 0.3)', justifyContent: 'flex-start' }}
            onClick={() => applyPreset('帮我下 60 盒 英伟达 RTX 5090 24GB AI算力显卡，申请打 9.5 折，送 1 年延保和 60 个显卡支架')}
          >
            <Cpu size={14} /> 用例 1: 5090显卡(支架赠品+库存60清空扣减)
          </button>
          <button 
            type="button" 
            className="btn" 
            style={{ fontSize: '0.75rem', padding: '0.45rem 0.65rem', backgroundColor: 'rgba(245, 158, 11, 0.15)', color: '#FBBF24', border: '1px solid rgba(245, 158, 11, 0.3)', justifyContent: 'flex-start' }}
            onClick={() => applyPreset('帮我下 100 台 远峰蓝苹果18，申请打 8.8 折，送 2 年延保和 100 个手机壳')}
          >
            <Smartphone size={14} /> 用例 2: 旗舰手机 (专属手机壳+延保)
          </button>
          <button 
            type="button" 
            className="btn" 
            style={{ fontSize: '0.75rem', padding: '0.45rem 0.65rem', backgroundColor: 'rgba(168, 85, 247, 0.15)', color: '#C084FC', border: '1px solid rgba(168, 85, 247, 0.3)', justifyContent: 'flex-start' }}
            onClick={() => applyPreset('帮我下 200 副 苹果 AirPods Pro 2 降噪耳机，申请打 9 折，送 1 年延保和 200 个保护套')}
          >
            <Headphones size={14} /> 用例 3: 蓝牙无线耳机 (专属硅胶保护套)
          </button>
          <button 
            type="button" 
            className="btn" 
            style={{ fontSize: '0.75rem', padding: '0.45rem 0.65rem', backgroundColor: 'rgba(59, 130, 246, 0.15)', color: '#60A5FA', border: '1px solid rgba(59, 130, 246, 0.3)', justifyContent: 'flex-start' }}
            onClick={() => applyPreset('帮我下 50 台 拯救者 Y9000P 游戏本，申请打 9.2 折，送 1 年延保、50 个电竞鼠标和 50 个机械键盘')}
          >
            <Laptop size={14} /> 用例 4: 笔记本电脑 (专属配套电竞鼠标+机械键盘)
          </button>
          <button 
            type="button" 
            className="btn" 
            style={{ fontSize: '0.75rem', padding: '0.45rem 0.65rem', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34D399', border: '1px solid rgba(16, 185, 129, 0.3)', justifyContent: 'flex-start' }}
            onClick={() => applyPreset('帮我下 100 片 三星 990 PRO 2TB 固态硬盘，申请打 9.5 折，送 1 年延保')}
          >
            <HardDrive size={14} /> 用例 5: DIY散件固态硬盘 (严格无赠品+延保)
          </button>
        </div>

        {/* 销售提单表单卡片 */}
        <div className="card" style={{ marginTop: '0.75rem' }}>
          {resubmitThreadId && activeReturnedTask && (
            <div className="sales-revision-workspace">
              {/* 主管整改要求指示卡片 */}
              <div className="sales-instruction-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ fontSize: '0.825rem', color: '#F87171', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertCircle size={14} /> 主管驳回整改指示 (第 {activeReturnedTask.revision_count || 1} 轮)
                  </strong>
                  <button 
                    type="button" 
                    onClick={cancelRevision}
                    style={{ background: 'transparent', border: 'none', color: '#FBBF24', cursor: 'pointer', fontSize: '0.75rem', textDecoration: 'underline' }}
                  >
                    取消修改
                  </button>
                </div>
                <div className="sales-instruction-text">
                  {activeReturnedTask.supervisor_instructions || '请调整报价与权益'}
                </div>

                {/* 智能一键采纳主管指标按钮 */}
                <button 
                  type="button" 
                  className="btn-adopt-instructions"
                  onClick={adoptSupervisorTargets}
                >
                  <Sparkles size={14} /> ✨ 一键按主管整改指标采纳并生成申请
                </button>
              </div>

              {/* 销售自主整改测算栏 (Sales Simulator) */}
              <div className="sales-sim-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '4px' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#FBBF24', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Sliders size={13} /> 销售自主微调测算栏 (Sales Sandbox)
                  </span>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    [{activeReturnedTask.opp_id}] {activeReturnedTask.product_name}
                  </span>
                </div>

                {/* 杠杆 1: 折扣微调 (支持输入任意字符，失焦软校验) */}
                <div className="sim-control-group" style={{ padding: '0.45rem 0.6rem', marginBottom: '0.45rem' }}>
                  <div className="sim-control-label" style={{ marginBottom: '2px', fontSize: '0.725rem' }}>
                    <span>申请折扣率 (Target Discount):</span>
                    <span className="value-preview">{(salesSimDiscount * 10).toFixed(1)} 折 ({(salesSimDiscount * 100).toFixed(0)}%)</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <input 
                      type="range" 
                      min="0.5" 
                      max="1.0" 
                      step="0.01" 
                      value={salesSimDiscount} 
                      onChange={e => {
                        const val = parseFloat(e.target.value);
                        setSalesSimDiscount(val);
                        setSalesSimDiscountStr(val.toString());
                      }}
                      style={{ flex: 1 }}
                    />
                    <input 
                      type="text" 
                      value={salesSimDiscountStr} 
                      onChange={e => {
                        setSalesSimDiscountStr(e.target.value);
                        const num = parseFloat(e.target.value);
                        if (!isNaN(num) && num >= 0.5 && num <= 1.0) {
                          setSalesSimDiscount(num);
                        }
                      }}
                      onBlur={() => {
                        let num = parseFloat(salesSimDiscountStr);
                        if (isNaN(num) || num < 0.5) num = 0.5;
                        else if (num > 1.0) num = 1.0;
                        num = Math.round(num * 100) / 100;
                        setSalesSimDiscount(num);
                        setSalesSimDiscountStr(num.toString());
                      }}
                      style={{ width: '55px', padding: '2px 4px', textAlign: 'center', fontSize: '0.75rem' }}
                    />
                  </div>
                </div>

                {/* 杠杆 2: 延保年数 */}
                <div className="sim-control-group" style={{ padding: '0.45rem 0.6rem', marginBottom: '0.45rem' }}>
                  <div className="sim-control-label" style={{ marginBottom: '2px', fontSize: '0.725rem' }}>
                    <span>附赠延保年数:</span>
                    <span className="value-preview">{salesSimWarrantyYears} 年 (折合: ¥{salesWarrantyCost.toLocaleString()})</span>
                  </div>
                  <div className="sim-stepper">
                    <button type="button" onClick={() => setSalesSimWarrantyYears(Math.max(0, salesSimWarrantyYears - 1))}>-</button>
                    <input 
                      type="number" 
                      min="0" 
                      max="5" 
                      value={salesSimWarrantyYears} 
                      onChange={e => setSalesSimWarrantyYears(Math.max(0, parseInt(e.target.value) || 0))}
                      style={{ width: '50px', padding: '2px', fontSize: '0.75rem' }}
                    />
                    <button type="button" onClick={() => setSalesSimWarrantyYears(salesSimWarrantyYears + 1)}>+</button>
                    <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginLeft: '4px' }}>
                      每年单台 ¥{salesWarrantyRate}
                    </span>
                  </div>
                </div>

                {/* 杠杆 3: 订购数量削减 (仅在缺口时解锁，只能减少不能增加) */}
                {salesHasShortage && (
                  <div className="sim-control-group" style={{ padding: '0.45rem 0.6rem', marginBottom: '0.45rem' }}>
                    <div className="sim-control-label" style={{ marginBottom: '2px', fontSize: '0.725rem' }}>
                      <span style={{ color: '#FB923C' }}>⚠️ 现货短缺，削减提货量:</span>
                      <span className="value-preview">{salesSimQuantity} 台 (可用现货: {salesCurrentStock} 台)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <div className="sim-stepper">
                        <button type="button" onClick={() => {
                          const q = Math.max(1, salesSimQuantity - 10);
                          setSalesSimQuantity(q);
                          setSalesSimQuantityStr(q.toString());
                        }}>-</button>
                        <input 
                          type="text" 
                          value={salesSimQuantityStr} 
                          onChange={e => {
                            setSalesSimQuantityStr(e.target.value);
                            const val = parseInt(e.target.value);
                            if (!isNaN(val) && val >= 1 && val <= salesOriginalQty) {
                              setSalesSimQuantity(val);
                            }
                          }}
                          onBlur={() => {
                            let val = parseInt(salesSimQuantityStr);
                            if (isNaN(val) || val < 1) val = 1;
                            else if (val > salesOriginalQty) val = salesOriginalQty;
                            setSalesSimQuantity(val);
                            setSalesSimQuantityStr(val.toString());
                          }}
                          style={{ width: '50px', padding: '2px', fontSize: '0.75rem' }}
                        />
                        <button 
                          type="button" 
                          disabled={salesSimQuantity >= salesOriginalQty}
                          onClick={() => {
                            const q = Math.min(salesOriginalQty, salesSimQuantity + 10);
                            setSalesSimQuantity(q);
                            setSalesSimQuantityStr(q.toString());
                          }}
                          style={{ opacity: salesSimQuantity >= salesOriginalQty ? 0.4 : 1 }}
                        >+</button>
                      </div>
                      <button 
                        type="button" 
                        className="btn"
                        style={{ fontSize: '0.68rem', padding: '2px 6px', backgroundColor: 'rgba(245, 158, 11, 0.2)', color: '#FBBF24', border: '1px solid rgba(245, 158, 11, 0.4)' }}
                        onClick={() => {
                          const q = Math.max(1, Math.min(salesCurrentStock, salesOriginalQty));
                          setSalesSimQuantity(q);
                          setSalesSimQuantityStr(q.toString());
                        }}
                      >
                        ⚡ 一键设为现货 ({salesCurrentStock}台)
                      </button>
                    </div>
                  </div>
                )}

                {/* 销售实时动态测算看板 */}
                <div className="sales-sim-grid">
                  <div className="sales-sim-item">
                    <span style={{ color: 'var(--text-muted)' }}>折后实收:</span>
                    <strong style={{ color: '#FBBF24' }}>¥{salesRevenue.toLocaleString()}</strong>
                  </div>
                  <div className="sales-sim-item">
                    <span style={{ color: 'var(--text-muted)' }}>履约总成本:</span>
                    <strong>¥{salesCombinedCost.toLocaleString()}</strong>
                  </div>
                  <div className="sales-sim-item">
                    <span style={{ color: 'var(--text-muted)' }}>真实净毛利:</span>
                    <strong style={{ color: salesTrueProfit >= 0 ? '#34D399' : '#F87171' }}>¥{salesTrueProfit.toLocaleString()}</strong>
                  </div>
                  <div className="sales-sim-item">
                    <span style={{ color: 'var(--text-muted)' }}>真实毛利率:</span>
                    <strong style={{ color: salesTrueMargin >= 15 ? '#34D399' : salesTrueMargin >= 0 ? '#FB923C' : '#F87171' }}>
                      {salesTrueMargin.toFixed(2)}%
                    </strong>
                  </div>
                </div>

                {/* 达标状态与同步按钮 */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                  <span style={{ fontSize: '0.72rem', color: salesTrueMargin >= 15 ? '#34D399' : '#F87171', fontWeight: 600 }}>
                    {salesTrueMargin >= 25 ? '🟢 正常放行线 (达标)' : salesTrueMargin >= 15 ? '🟡 主管要求线 (达标中度)' : '🟠 仍低于15% (建议继续调高)'}
                  </span>
                  <button 
                    type="button" 
                    className="btn" 
                    style={{ fontSize: '0.72rem', padding: '3px 8px', backgroundColor: 'rgba(99, 102, 241, 0.25)', color: '#A5B4FC', border: '1px solid rgba(99, 102, 241, 0.4)' }}
                    onClick={syncSalesSimToText}
                  >
                    📝 同步测算至提单文本
                  </button>
                </div>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>{resubmitThreadId ? '按主管要求修改提单内容 (可自由编辑或由上方测算栏同步)' : '自然语言输入提单申请'}</span>
                <button
                  type="button"
                  onClick={() => openFallbackModal('销售主动切换为高可靠结构化表单录入')}
                  style={{
                    background: 'transparent',
                    border: '1px dashed rgba(99, 102, 241, 0.4)',
                    color: '#A5B4FC',
                    borderRadius: '4px',
                    padding: '2px 8px',
                    fontSize: '0.72rem',
                    cursor: 'pointer'
                  }}
                >
                  📋 切换为标准结构化表单
                </button>
              </label>
              <textarea 
                rows={3}
                value={salesInput}
                onChange={e => setSalesInput(e.target.value)}
                placeholder="例如：帮我下 500 台 远峰蓝苹果18，申请打 9 折，承诺送 1 年延保和 250 个保护壳"
                style={{ borderColor: resubmitThreadId ? '#F59E0B' : undefined }}
              />
            </div>

            {/* SSE 流式心跳推进状态卡片 */}
            {streamProgressMsg && (
              <div style={{
                marginBottom: '0.75rem',
                padding: '0.6rem 0.8rem',
                backgroundColor: 'rgba(99, 102, 241, 0.12)',
                border: '1px solid rgba(99, 102, 241, 0.3)',
                borderRadius: '6px',
                fontSize: '0.8rem',
                color: '#C7D2FE',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <RefreshCw className="spin" size={14} color="#818CF8" />
                <span>{streamProgressMsg}</span>
              </div>
            )}

            <button 
              type="submit" 
              className={`btn ${resubmitThreadId ? 'btn-success' : 'btn-primary'}`} 
              disabled={isSubmitting}
              style={{ width: '100%' }}
            >
              {isSubmitting ? <RefreshCw className="spin" size={18} /> : resubmitThreadId ? <RotateCcw size={18} /> : <Send size={18} />}
              {isSubmitting ? 'Agent 正在穿透核算财务与风控...' : resubmitThreadId ? '重新提交主管二次审批 (Resubmit)' : '提交给 Agent 分析'}
            </button>
          </form>

          {submitResult && (
            <div style={{ marginTop: '1rem' }}>
              <div className={`status-badge ${submitResult.status === 'COMPLETED' ? 'success' : ''}`}>
                {submitResult.status === 'COMPLETED' ? <CheckCircle2 size={14} /> : <Clock size={14} />}
                状态: {submitResult.status}
              </div>
              <p style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                {submitResult.message}
              </p>
            </div>
          )}
        </div>

        {/* 业务体验层：兜底降级结构化提单表单弹窗 (Fallback Form) */}
        {isFallbackFormOpen && (
          <div className="modal-overlay" style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            backdropFilter: 'blur(4px)'
          }}>
            <div style={{
              backgroundColor: '#1E293B',
              border: '1px solid #334155',
              borderRadius: '12px',
              padding: '1.5rem',
              maxWidth: '540px',
              width: '90%',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#F8FAFC', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShieldCheck size={20} color="#34D399" /> 生产高可用降级：标准结构化提单表单
                </h3>
                <button
                  onClick={() => setIsFallbackFormOpen(false)}
                  style={{ background: 'transparent', border: 'none', color: '#94A3B8', fontSize: '1.2rem', cursor: 'pointer' }}
                >×</button>
              </div>

              {fallbackReason && (
                <div style={{
                  padding: '0.6rem 0.8rem',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  color: '#FCA5A5',
                  marginBottom: '1rem'
                }}>
                  <strong>⚠️ 触发原因：</strong>{fallbackReason}
                </div>
              )}

              <p style={{ fontSize: '0.825rem', color: '#94A3B8', marginBottom: '1.2rem' }}>
                当大模型接口超时或触发熔断时，系统自动无缝切换为此标准表单。请直接选择商品物料并配置商务参数，系统将直接穿透底层数据库提交，业务绝不中断！
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                {/* 1. 标的商品物料输入栏 (可搜索、点击候选自动填入、失焦清空防呆) */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <label style={{ fontSize: '0.8rem', color: '#CBD5E1', fontWeight: 500 }}>
                      标的商品物料 (SKU Catalog):
                    </label>
                    {isSkuConfirmed && fallbackSelectedSku ? (
                      <span style={{ fontSize: '0.72rem', color: '#34D399', display: 'flex', alignItems: 'center', gap: '3px' }}>
                        ✓ 已绑定官方SKU
                      </span>
                    ) : fallbackSearchQuery.trim() ? (
                      <span style={{ fontSize: '0.72rem', color: filteredProductList.length > 0 ? '#60A5FA' : '#F87171' }}>
                        {filteredProductList.length > 0 ? `候选 ${filteredProductList.length} 款 (请点击选中)` : '无匹配商品'}
                      </span>
                    ) : null}
                  </div>

                  {/* 搜索与填入输入框容器 */}
                  <div style={{ position: 'relative' }}>
                    <Search size={16} color={isSkuConfirmed ? "#10B981" : "#94A3B8"} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
                    <input
                      type="text"
                      value={fallbackSearchQuery}
                      onChange={e => handleSkuInputChange(e.target.value)}
                      onFocus={() => setIsSkuDropdownOpen(true)}
                      onBlur={handleSkuInputBlur}
                      placeholder="搜索主商品物料，点击下方候选自动填入 (随意输入失焦自动清空)"
                      style={{
                        width: '100%',
                        padding: '8px 30px 8px 32px',
                        backgroundColor: '#0F172A',
                        border: isSkuConfirmed ? '1px solid #10B981' : (fallbackSearchQuery.trim() && filteredProductList.length === 0 ? '1px solid #EF4444' : '1px solid #3B82F6'),
                        borderRadius: '6px',
                        color: '#F8FAFC',
                        fontSize: '0.85rem',
                        outline: 'none',
                        boxShadow: isSkuConfirmed ? '0 0 0 1px rgba(16, 185, 129, 0.25)' : (fallbackSearchQuery.trim() && filteredProductList.length === 0 ? '0 0 0 2px rgba(239, 68, 68, 0.25)' : '0 0 0 1px rgba(59, 130, 246, 0.2)')
                      }}
                    />
                    {fallbackSearchQuery && (
                      <button
                        type="button"
                        onMouseDown={e => {
                          e.preventDefault();
                          setFallbackSearchQuery('');
                          setFallbackSelectedSku('');
                          setIsSkuConfirmed(false);
                          setFallbackFreebieName('');
                          setFallbackFreebieQty(0);
                        }}
                        style={{
                          position: 'absolute',
                          right: '8px',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          background: 'none',
                          border: 'none',
                          color: '#94A3B8',
                          cursor: 'pointer',
                          fontSize: '0.85rem',
                          padding: '2px'
                        }}
                        title="清空重选"
                      >
                        ✕
                      </button>
                    )}

                    {/* 搜索候选下拉浮层：仅允许销售点击搜索到的真实商品自动填入 */}
                    {isSkuDropdownOpen && (
                      <div style={{
                        position: 'absolute',
                        top: '100%',
                        left: 0,
                        right: 0,
                        zIndex: 100,
                        maxHeight: '220px',
                        overflowY: 'auto',
                        backgroundColor: '#0F172A',
                        border: '1px solid #3B82F6',
                        borderRadius: '6px',
                        marginTop: '4px',
                        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.8)'
                      }}>
                        {filteredProductList.length > 0 ? (
                          filteredProductList.map(p => {
                            const isCurrentSelected = p.opp_id === fallbackSelectedSku && isSkuConfirmed;
                            return (
                              <div
                                key={p.opp_id}
                                className="sku-candidate-item"
                                data-opp-id={p.opp_id}
                                onMouseDown={e => {
                                  e.preventDefault(); // 阻止 input blur，确保先执行点击填入
                                  handleSelectProduct(p);
                                }}
                                onClick={() => handleSelectProduct(p)}
                                style={{
                                  padding: '8px 12px',
                                  fontSize: '0.82rem',
                                  cursor: 'pointer',
                                  borderBottom: '1px solid #1E293B',
                                  backgroundColor: isCurrentSelected ? 'rgba(59, 130, 246, 0.25)' : 'transparent',
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                  transition: 'background-color 0.15s'
                                }}
                                onMouseEnter={e => (e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.2)')}
                                onMouseLeave={e => (e.currentTarget.style.backgroundColor = isCurrentSelected ? 'rgba(59, 130, 246, 0.25)' : 'transparent')}
                              >
                                <div>
                                  <span style={{ color: '#60A5FA', fontWeight: 600, marginRight: '6px' }}>[{p.opp_id}]</span>
                                  <span style={{ color: '#F8FAFC' }}>{p.product_name}</span>
                                </div>
                                <div style={{ fontSize: '0.72rem', color: '#94A3B8', whiteSpace: 'nowrap', marginLeft: '8px' }}>
                                  单价: <span style={{ color: '#F8FAFC' }}>¥{p.price?.toLocaleString()}</span> | 现存: <span style={{ color: '#34D399' }}>{p.stock}{p.unit}</span>
                                </div>
                              </div>
                            );
                          })
                        ) : (
                          <div
                            onMouseDown={e => e.preventDefault()}
                            style={{ padding: '10px 12px', fontSize: '0.8rem', color: '#F87171', textAlign: 'center' }}
                          >
                            未检索到匹配的官方商品物料（失焦将自动清空内容）
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* 核心红框告警：当输入内容在数据库中检索不到时，明确提示销售人员 */}
                  {fallbackSearchQuery.trim() && filteredProductList.length === 0 && (
                    <div style={{
                      padding: '0.65rem 0.8rem',
                      backgroundColor: 'rgba(239, 68, 68, 0.12)',
                      border: '1px solid rgba(239, 68, 68, 0.4)',
                      borderRadius: '6px',
                      marginTop: '6px',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '8px'
                    }}>
                      <AlertCircle size={16} color="#EF4444" style={{ flexShrink: 0, marginTop: '1px' }} />
                      <div style={{ fontSize: '0.78rem', color: '#FCA5A5', lineHeight: '1.4' }}>
                        <div style={{ fontWeight: 600, color: '#EF4444' }}>
                          该商品不存在或尚未录入系统！
                        </div>
                        <div>
                          物料库中未收录与 <strong>"{fallbackSearchQuery.trim()}"</strong> 匹配的商品。销售人员仅可填入已收录商品，点击空白处输入框将自动清空。
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 当前选中官方商品的参数指标微卡片 */}
                  {(() => {
                    const sel = productList.find(p => p.opp_id === fallbackSelectedSku);
                    if (!sel || !isSkuConfirmed) return null;
                    return (
                      <div style={{
                        marginTop: '6px',
                        padding: '6px 10px',
                        backgroundColor: 'rgba(15, 23, 42, 0.6)',
                        border: '1px dashed #334155',
                        borderRadius: '6px',
                        fontSize: '0.72rem',
                        display: 'flex',
                        justifyContent: 'space-between',
                        color: '#94A3B8'
                      }}>
                        <span>商机: <strong style={{ color: '#60A5FA' }}>{sel.opp_id}</strong></span>
                        <span>指导单价: <strong style={{ color: '#F8FAFC' }}>¥{sel.price.toLocaleString()}</strong></span>
                        <span>BOM底价: <strong style={{ color: '#FCD34D' }}>¥{sel.cost_price?.toLocaleString()}</strong></span>
                        <span>可用现货: <strong style={{ color: sel.stock >= fallbackQuantity ? '#34D399' : '#EF4444' }}>{sel.stock} {sel.unit}</strong></span>
                      </div>
                    );
                  })()}
                </div>

                {/* 2. 商务参数：订购数量与申请折扣率 */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.8rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#CBD5E1', marginBottom: '4px' }}>订购数量:</label>
                    <input
                      type="number"
                      min={1}
                      value={fallbackQuantity}
                      onChange={e => {
                        const newQ = Math.max(1, parseInt(e.target.value) || 1);
                        setFallbackQuantity(newQ);
                        // 如果是单赠品且已有默认赠品且数量大于0，同步更新赠品数量
                        if (fallbackFreebieName && fallbackFreebieQty > 0) {
                          setFallbackFreebieQty(newQ);
                        }
                      }}
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        backgroundColor: '#0F172A',
                        border: '1px solid #334155',
                        borderRadius: '6px',
                        color: '#F8FAFC',
                        fontSize: '0.85rem'
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#CBD5E1', marginBottom: '4px' }}>申请折扣率 (0.50 ~ 1.00):</label>
                    <input
                      type="number"
                      min={0.5}
                      max={1.0}
                      step={0.01}
                      value={fallbackDiscount}
                      onChange={e => setFallbackDiscount(parseFloat(e.target.value) || 1.0)}
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        backgroundColor: '#0F172A',
                        border: '1px solid #334155',
                        borderRadius: '6px',
                        color: '#F8FAFC',
                        fontSize: '0.85rem'
                      }}
                    />
                  </div>
                </div>

                {/* 3. 商业延保年限 */}
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#CBD5E1', marginBottom: '4px' }}>赠送商业延保 (年):</label>
                  <select
                    value={fallbackWarranty}
                    onChange={e => setFallbackWarranty(parseInt(e.target.value) || 0)}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      backgroundColor: '#0F172A',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      color: '#F8FAFC',
                      fontSize: '0.85rem'
                    }}
                  >
                    <option value={0}>不附赠延保 (0年)</option>
                    <option value={1}>1 年商业延保 (标准)</option>
                    <option value={2}>2 年商业延保</option>
                    <option value={3}>3 年商业延保</option>
                  </select>
                </div>

                {/* 4. 专属赠品区域（如图二：品类动态联动——多种展开选择、单项默认填入、无赠品默认空白锁定） */}
                {(() => {
                  const selProd = productList.find(p => p.opp_id === fallbackSelectedSku);
                  const rule = selProd && isSkuConfirmed
                    ? getProductFreebieRule(selProd.product_name, selProd.category_lvl1 || selProd.category || '')
                    : null;

                  return (
                    <div style={{
                      padding: '10px 12px',
                      backgroundColor: 'rgba(15, 23, 42, 0.7)',
                      border: '1px solid #334155',
                      borderRadius: '8px'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <label style={{ fontSize: '0.8rem', color: '#CBD5E1', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>🎁 专属赠品配置 (品类自动联动):</span>
                          {rule && (
                            <span style={{
                              fontSize: '0.7rem',
                              padding: '1px 6px',
                              borderRadius: '4px',
                              backgroundColor: rule.type === 'none' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(59, 130, 246, 0.2)',
                              color: rule.type === 'none' ? '#F87171' : '#60A5FA'
                            }}>
                              {rule.type === 'multiple' ? '多种赠品可选 (点击展开)' : rule.type === 'single' ? '单一赠品 (默认自动填入)' : '核心硬件严禁赠品'}
                            </span>
                          )}
                        </label>
                        {fallbackFreebieName && fallbackFreebieQty > 0 && (
                          <span style={{ fontSize: '0.72rem', color: '#34D399' }}>
                            已配: {fallbackFreebieQty} 个 {fallbackFreebieName}
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '0.8rem' }}>
                        {/* 赠品类别栏 */}
                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', color: '#94A3B8', marginBottom: '4px' }}>
                            赠品类别:
                          </label>
                          {!selProd || !isSkuConfirmed ? (
                            <input
                              type="text"
                              disabled
                              value=""
                              placeholder="-- 请先在上方搜索并选择主商品物料 --"
                              style={{
                                width: '100%',
                                padding: '8px 10px',
                                backgroundColor: '#1E293B',
                                border: '1px solid #334155',
                                borderRadius: '6px',
                                color: '#64748B',
                                fontSize: '0.82rem',
                                cursor: 'not-allowed'
                              }}
                            />
                          ) : rule?.type === 'none' ? (
                            <input
                              type="text"
                              disabled
                              value=""
                              placeholder="🚫 该商品品类严禁附赠配件 (默认空白)"
                              style={{
                                width: '100%',
                                padding: '8px 10px',
                                backgroundColor: '#1E293B',
                                border: '1px solid #334155',
                                borderRadius: '6px',
                                color: '#94A3B8',
                                fontSize: '0.82rem',
                                cursor: 'not-allowed'
                              }}
                            />
                          ) : rule?.type === 'single' ? (
                            /* 对应一种赠品：默认自动填入，也可以不填入 */
                            <select
                              value={fallbackFreebieName}
                              onChange={e => {
                                const val = e.target.value;
                                setFallbackFreebieName(val);
                                if (!val) {
                                  setFallbackFreebieQty(0);
                                } else if (fallbackFreebieQty === 0) {
                                  setFallbackFreebieQty(fallbackQuantity);
                                }
                              }}
                              style={{
                                width: '100%',
                                padding: '8px 10px',
                                backgroundColor: '#0F172A',
                                border: '1px solid #3B82F6',
                                borderRadius: '6px',
                                color: '#F8FAFC',
                                fontSize: '0.85rem'
                              }}
                            >
                              <option value={rule.defaultFreebie}>
                                🎁 {rule.defaultFreebie} (默认自动填入)
                              </option>
                              <option value="">
                                ❌ 不附赠此赠品 (0件)
                              </option>
                            </select>
                          ) : (
                            /* 对应多种赠品：点击之后向下展开所有赠品，点击自动填入 */
                            <select
                              value={fallbackFreebieName}
                              onChange={e => {
                                const val = e.target.value;
                                setFallbackFreebieName(val);
                                if (!val) {
                                  setFallbackFreebieQty(0);
                                } else if (fallbackFreebieQty === 0) {
                                  setFallbackFreebieQty(fallbackQuantity);
                                }
                              }}
                              style={{
                                width: '100%',
                                padding: '8px 10px',
                                backgroundColor: '#0F172A',
                                border: '1px solid #3B82F6',
                                borderRadius: '6px',
                                color: '#F8FAFC',
                                fontSize: '0.85rem'
                              }}
                            >
                              <option value="">-- 点击向下展开所有可选赠品 --</option>
                              {rule?.allowedFreebies.map((fName: string) => (
                                <option key={fName} value={fName}>
                                  🎁 {fName}
                                </option>
                              ))}
                              <option value="">❌ 不附赠任何赠品</option>
                            </select>
                          )}
                        </div>

                        {/* 专属赠品数量 */}
                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', color: '#94A3B8', marginBottom: '4px' }}>
                            专属赠品数量:
                          </label>
                          <input
                            type="number"
                            min={0}
                            disabled={!selProd || !isSkuConfirmed || rule?.type === 'none' || !fallbackFreebieName}
                            value={(!selProd || !isSkuConfirmed || rule?.type === 'none' || !fallbackFreebieName) ? 0 : fallbackFreebieQty}
                            onChange={e => setFallbackFreebieQty(Math.max(0, parseInt(e.target.value) || 0))}
                            placeholder={(!selProd || rule?.type === 'none') ? '无赠品' : '赠品数量'}
                            style={{
                              width: '100%',
                              padding: '8px 10px',
                              backgroundColor: (!selProd || !isSkuConfirmed || rule?.type === 'none' || !fallbackFreebieName) ? '#1E293B' : '#0F172A',
                              border: '1px solid #334155',
                              borderRadius: '6px',
                              color: (!selProd || !isSkuConfirmed || rule?.type === 'none' || !fallbackFreebieName) ? '#64748B' : '#F8FAFC',
                              fontSize: '0.85rem',
                              cursor: (!selProd || !isSkuConfirmed || rule?.type === 'none' || !fallbackFreebieName) ? 'not-allowed' : 'text'
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })()}

                {/* 5. 底部操作按钮 */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.8rem' }}>
                  <button
                    type="button"
                    onClick={() => setIsFallbackFormOpen(false)}
                    style={{
                      padding: '8px 14px',
                      backgroundColor: 'transparent',
                      border: '1px solid #475569',
                      borderRadius: '6px',
                      color: '#CBD5E1',
                      cursor: 'pointer'
                    }}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    disabled={!isSkuConfirmed || !productList.find(p => p.opp_id === fallbackSelectedSku)}
                    onClick={async () => {
                      const selectedProd = productList.find(p => p.opp_id === fallbackSelectedSku);
                      if (!selectedProd || !isSkuConfirmed) return;
                      const prodName = selectedProd.product_name;
                      const unit = selectedProd.unit || '台';
                      const discStr = fallbackDiscount < 1.0 ? `，申请打 ${(fallbackDiscount * 10).toFixed(1)} 折` : '';
                      const warStr = fallbackWarranty > 0 ? `，并送 ${fallbackWarranty} 年延保` : '';
                      const fbStr = (fallbackFreebieName && fallbackFreebieQty > 0)
                        ? `和 ${fallbackFreebieQty} 个 ${fallbackFreebieName}`
                        : '';
                      
                      const assembled = `帮我下 ${fallbackQuantity} ${unit} ${prodName}${discStr}${warStr}${fbStr}`;
                      setSalesInput(assembled);
                      setIsFallbackFormOpen(false);
                      await doActualSubmit(assembled);
                    }}
                    style={{
                      padding: '8px 18px',
                      backgroundColor: (!isSkuConfirmed || !productList.find(p => p.opp_id === fallbackSelectedSku)) ? '#475569' : '#3B82F6',
                      border: 'none',
                      borderRadius: '6px',
                      color: '#FFFFFF',
                      fontWeight: 600,
                      cursor: (!isSkuConfirmed || !productList.find(p => p.opp_id === fallbackSelectedSku)) ? 'not-allowed' : 'pointer',
                      opacity: (!isSkuConfirmed || !productList.find(p => p.opp_id === fallbackSelectedSku)) ? 0.6 : 1
                    }}
                  >
                    {(!isSkuConfirmed || !productList.find(p => p.opp_id === fallbackSelectedSku)) ? '⚠️ 请在上方选择有效商品' : '🚀 确定生成并提交提单'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}


        {/* 销售端专属：待我修改 (Returned for Revision) 区域 */}
        <div className="returned-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h3 style={{ fontSize: '0.9rem', color: '#F87171', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <AlertCircle size={16} /> 待我修改 (Returned for Revision)
            </h3>
            <span className="returned-badge">{returnedTasks.length} 项待改</span>
          </div>

          {returnedTasks.length === 0 ? (
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center', padding: '0.75rem 0' }}>
              暂无被主管驳回的提单，所有申请均在正常流转中
            </p>
          ) : (
            returnedTasks.map(t => (
              <div key={t.thread_id} className="returned-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#60A5FA', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span className="task-id" style={{ backgroundColor: 'rgba(59, 130, 246, 0.2)', padding: '2px 6px', borderRadius: '4px' }}>
                      #{t.order_id || (t.thread_id.startsWith('th-') ? t.thread_id.split('-')[1] : t.thread_id)}
                    </span>
                    <span style={{ fontSize: '0.825rem', color: 'var(--text-main)', fontWeight: 600 }}>[{t.opp_id}] {t.product_name}</span>
                  </span>
                  <span className="returned-badge">第 {t.revision_count || 0} 轮驳回</span>
                </div>

                <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '6px' }}>
                  <Clock size={12} color="#94A3B8" /> 下单时间: {t.created_at || '刚刚'}
                </div>

                <div className="revision-instruction-box">
                  <strong>主管意见：</strong>"{t.supervisor_instructions || '请调整报价与权益'}"
                </div>

                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <span>原申请折扣: {((t.requested_discount || 1)*10).toFixed(1)}折</span>
                  <span>原真实毛利率: {(t.true_margin || 0).toFixed(1)}%</span>
                </div>

                <button 
                  type="button" 
                  className="btn" 
                  style={{ width: '100%', fontSize: '0.775rem', padding: '0.45rem', backgroundColor: 'rgba(239, 68, 68, 0.2)', color: '#F87171', border: '1px solid rgba(239, 68, 68, 0.4)' }}
                  onClick={() => handleLoadRevision(t)}
                >
                  <RotateCcw size={14} /> 一键载入并按要求修改
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* ================= 右侧：主管 Deal Desk 审批工作台 ================= */}
      <main className="right-panel panel">
        <header>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h1><Inbox size={26} /> 主管 Deal Desk 审批工作台</h1>
              <p className="subtitle">3C 电子硬件穿透 | 双向协同流转中心 (待主管审批: {tasks.length})</p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                type="button"
                className="btn"
                style={{ fontSize: '0.75rem', padding: '4px 10px', backgroundColor: 'rgba(59, 130, 246, 0.15)', color: '#60A5FA', border: '1px solid rgba(59, 130, 246, 0.3)' }}
                onClick={async () => {
                  try {
                    const res = await axios.post('/api/products/restock');
                    alert(res.data.message || '演示库存已成功重置！');
                    fetchAllTasks();
                  } catch (e) {
                    alert('重置库存失败，请检查后端状态');
                  }
                }}
                title="一键将所有 33 款商品与赠品恢复至标准初始库存"
              >
                <Package size={14} /> 一键重置演示库存
              </button>
              <div className="status-badge">
                <RefreshCw size={14} className="spin" />
                双向协同轮询中
              </div>
            </div>
          </div>

          {/* 风险等级分级准则卡尺 */}
          <div className="risk-legend-bar">
            <span className="legend-label"><Info size={14} /> 防资损毛利率红线标准：</span>
            <div className="legend-pill normal">🟢 正常：≥ 25% (达标自动放行)</div>
            <div className="legend-pill medium">🟡 中度风险：15% ~ 25% (总监常规审批)</div>
            <div className="legend-pill high">🟠 偏高风险：0% ~ 15% (VP战略特批)</div>
            <div className="legend-pill critical">🔴 极高风险：&lt; 0% 击穿BOM成本 (CFO一票否决)</div>
          </div>
        </header>

        {tasks.length === 0 ? (
          <div className="empty-state">
            <Inbox size={64} />
            <p>当前没有待主管审批的任务，所有合规提单已自动流转放行</p>
          </div>
        ) : (
          <div className="task-grid">
            {tasks.map(task => {
              const data = task.interrupt_data;
              const isCritical = data.margin_risk_level === 'CRITICAL_LOSS' || (data.true_profit !== undefined && data.true_profit < 0);
              const isVp = !isCritical && ((data.margin_risk_level === 'VP_SPECIAL') || (data.true_margin !== undefined && data.true_margin < 15));
              const isDirector = !isCritical && !isVp && ((data.margin_risk_level === 'DIRECTOR_REVIEW') || (data.true_margin !== undefined && data.true_margin < 25));
              
              const trueMargin = data.true_margin ?? 0;
              const trueProfit = data.true_profit ?? 0;
              const concessions = (data.warranty_total_cost || 0) + (data.freebie_total_cost || 0);

              return (
                <div 
                  key={task.thread_id} 
                  className={`card task-card ${selectedTask?.thread_id === task.thread_id ? 'active' : ''}`}
                  onClick={() => openDrawer(task)}
                >
                  <div className="task-header" style={{ alignItems: 'flex-start' }}>
                    <div 
                      className={`status-badge ${isCritical ? 'risk-badge-critical' : ''}`} 
                      style={{ 
                        color: isCritical ? '#EF4444' : isVp ? '#FB923C' : isDirector ? '#FACC15' : '#34D399', 
                        backgroundColor: isCritical ? 'rgba(239, 68, 68, 0.25)' : isVp ? 'rgba(245, 158, 11, 0.2)' : isDirector ? 'rgba(234, 179, 8, 0.18)' : 'rgba(16, 185, 129, 0.15)',
                        border: isCritical ? '1px solid #EF4444' : undefined,
                        fontWeight: 600
                      }}
                    >
                      {isCritical ? <ShieldAlert size={14} /> : <AlertTriangle size={14} />} 
                      {isCritical ? '🔴 极高风险 (击穿BOM倒贴)' : isVp ? '🟠 偏高风险 (VP特批)' : isDirector ? '🟡 中度风险 (总监审批)' : '🟢 正常 (达标高毛利)'}
                      {(data.revision_count || 0) > 0 && <span style={{ marginLeft: '4px', opacity: 0.85 }}>(第{data.revision_count}次修改提单)</span>}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '3px' }}>
                      <span className="task-id" style={{ fontWeight: 700, fontSize: '0.85rem', color: '#60A5FA', letterSpacing: '0.5px' }}>
                        #{task.order_id || (task.thread_id.startsWith('th-') ? task.thread_id.split('-')[1] : task.thread_id)}
                      </span>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '3px' }}>
                        <Clock size={11} /> {task.created_at || '刚刚'}
                      </span>
                    </div>
                  </div>

                  <div className="task-body">
                    <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.6rem' }}>
                      [{data.opp_id}] {data.product_name || '待定商品'}
                    </h4>

                    {/* 核心财务指标穿透 */}
                    <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
                      <div className={`margin-pill ${isCritical ? 'critical' : trueMargin < 15 ? 'warning' : 'success'}`}>
                        {trueMargin < 0 ? <TrendingDown size={14} /> : <TrendingUp size={14} />}
                        真实毛利率: {trueMargin.toFixed(1)}%
                      </div>
                      <div className="margin-pill" style={{ backgroundColor: 'rgba(255,255,255,0.06)', color: 'var(--text-main)' }}>
                        <DollarSign size={14} />
                        净毛利: ¥{trueProfit.toLocaleString()}
                      </div>
                    </div>

                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: '1.6' }}>
                      <p>📦 订购数量: <strong style={{ color: 'var(--text-main)' }}>{data.quantity || 1} {data.unit || '台'}</strong> (单价 ¥{(data.unit_price || 0).toLocaleString()} | BOM底价 ¥{(data.cost_price || 0).toLocaleString()})</p>
                      <p>💰 合同实收: <strong style={{ color: 'var(--text-main)' }}>¥{(data.final_amount || 0).toLocaleString()}</strong> (申请折扣 {((data.requested_discount || 1) * 10).toFixed(1)} 折)</p>
                      
                      {concessions > 0 && (
                        <p style={{ color: '#FBBF24', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                          <Gift size={13} /> 隐形让利侵蚀: -¥{concessions.toLocaleString()} 
                          {data.warranty_years ? ` (含${data.warranty_years}年延保)` : ''}
                          {data.freebie_total_cost ? ` (含赠品)` : ''}
                        </p>
                      )}
                    </div>

                    {/* 库存状态指示徽章 */}
                    {data.stock_status === 'SHORTAGE' ? (
                      <div style={{ marginTop: '0.5rem', padding: '4px 8px', borderRadius: '4px', fontSize: '0.75rem', backgroundColor: 'rgba(245, 158, 11, 0.15)', color: '#F59E0B', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <AlertTriangle size={12} /> 现货库存不足 (现存 {data.current_stock || 0}{data.unit}, 缺口 {data.shortage_qty || 0}{data.unit})
                      </div>
                    ) : (
                      <div style={{ marginTop: '0.5rem', padding: '4px 8px', borderRadius: '4px', fontSize: '0.75rem', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#10B981', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <CheckCircle2 size={12} /> 现货充沛 (可用库存 {data.current_stock || 0}{data.unit})
                      </div>
                    )}

                    {/* 风控红线标签 */}
                    <div style={{ marginTop: '0.6rem', display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {(data.risk_reasons || [data.reason]).map((r, idx) => (
                        <span 
                          key={idx} 
                          style={{ 
                            fontSize: '0.7rem', 
                            padding: '2px 6px', 
                            borderRadius: '3px', 
                            backgroundColor: r.includes('击穿') || r.includes('严重资损') ? 'rgba(239, 68, 68, 0.25)' : 'rgba(245, 158, 11, 0.15)', 
                            color: r.includes('击穿') || r.includes('严重资损') ? '#F87171' : '#FBBF24' 
                          }}
                        >
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div style={{ marginTop: '1rem', borderTop: '1px solid var(--border)', paddingTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    原申请："{(task.current_values.sales_input || '').substring(0, 26)}..."
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {/* ================= 抽屉：Executive Deal Desk 双向决策审批面板 ================= */}
      {selectedTask && (
        <div className="drawer-overlay" onClick={() => !isResuming && setSelectedTask(null)}>
          <div className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer-header">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h2>3C 防资损 Deal Desk 协同审批</h2>
                  <span className="task-id" style={{ backgroundColor: 'rgba(59, 130, 246, 0.2)', color: '#60A5FA', padding: '2px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 700 }}>
                    #{selectedTask.order_id || (selectedTask.thread_id.startsWith('th-') ? selectedTask.thread_id.split('-')[1] : selectedTask.thread_id)}
                  </span>
                </div>
                <p className="subtitle" style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '3px' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '3px', color: '#93C5FD' }}><Clock size={11} /> 下单时间: {selectedTask.created_at || '刚刚'}</span>
                  <span>|</span>
                  <span>BOM 硬件底线成本穿透与隐形变相让利风控</span>
                </p>
              </div>
              <button className="drawer-close" onClick={() => setSelectedTask(null)} disabled={isResuming}>
                <X size={20} />
              </button>
            </div>

            <div className="drawer-content">
              {/* 抽屉内风控准则标准条 */}
              <div className="risk-legend-bar" style={{ marginTop: '0', marginBottom: '0.85rem' }}>
                <span className="legend-label"><Info size={12} /> 毛利红线：</span>
                <span className="legend-pill normal">≥25% 正常</span>
                <span className="legend-pill medium">15%~25% 中度</span>
                <span className="legend-pill high">0%~15% 偏高</span>
                <span className="legend-pill critical">&lt;0% 极高/倒贴</span>
              </div>

              {/* 商业博弈恢复建议 */}
              {selectedTask.interrupt_data.recovery_suggestions && selectedTask.interrupt_data.recovery_suggestions.length > 0 && (
                <div className="suggestion-box">
                  <div className="suggestion-title">
                    <Sparkles size={14} /> 智能商业决策与毛利恢复建议:
                  </div>
                  {selectedTask.interrupt_data.recovery_suggestions.map((s, idx) => (
                    <div key={idx} className="suggestion-item">
                      • {s}
                    </div>
                  ))}
                </div>
              )}

              {/* 全景财务成本穿透表 */}
              <div className="card" style={{ marginBottom: '1.25rem', backgroundColor: 'rgba(0,0,0,0.25)' }}>
                <h3 style={{ fontSize: '0.85rem', marginBottom: '0.6rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <TrendingUp size={15} /> 综合收益与成本穿透清单 (True Margin Breakdown)
                </h3>
                
                <div className="data-row">
                  <span className="data-label">标的商品</span>
                  <span className="data-value">[{selectedTask.interrupt_data.opp_id}] {selectedTask.interrupt_data.product_name}</span>
                </div>
                <div className="data-row">
                  <span className="data-label">订购量词</span>
                  <span className="data-value">{selectedTask.interrupt_data.quantity || 1} {selectedTask.interrupt_data.unit || '台'}</span>
                </div>
                <div className="data-row">
                  <span className="data-label">官方标价 (单价)</span>
                  <span className="data-value">¥{(selectedTask.interrupt_data.unit_price || 0).toLocaleString()}</span>
                </div>
                <div className="data-row">
                  <span className="data-label">合同折后实收 (Revenue)</span>
                  <span className="data-value highlight">¥{(selectedTask.interrupt_data.final_amount || 0).toLocaleString()} ({((selectedTask.interrupt_data.requested_discount || 1)*10).toFixed(1)}折)</span>
                </div>
                
                <div className="data-row">
                  <span className="data-label">硬件 BOM 底线成本</span>
                  <span className="data-value">¥{(selectedTask.interrupt_data.bom_total_cost || 0).toLocaleString()} (单台底价 ¥{(selectedTask.interrupt_data.cost_price || 0).toLocaleString()})</span>
                </div>

                {selectedTask.interrupt_data.warranty_years ? (
                  <div className="data-row">
                    <span className="data-label">附赠延保折合成本</span>
                    <span className="data-value" style={{ color: '#FBBF24' }}>
                      + ¥{(selectedTask.interrupt_data.warranty_total_cost || 0).toLocaleString()} (赠{selectedTask.interrupt_data.warranty_years}年 @ ¥{selectedTask.interrupt_data.warranty_cost_per_year}/台/年)
                    </span>
                  </div>
                ) : null}

                {selectedTask.interrupt_data.freebie_total_cost ? (
                  <div className="data-row">
                    <span className="data-label">捆绑赠品配件成本</span>
                    <span className="data-value" style={{ color: '#FBBF24' }}>
                      + ¥{(selectedTask.interrupt_data.freebie_total_cost || 0).toLocaleString()} (附赠配件清单)
                    </span>
                  </div>
                ) : null}

                <div className="data-row">
                  <span className="data-label">综合履约总成本 (Total Cost)</span>
                  <span className="data-value" style={{ fontWeight: 600 }}>¥{(selectedTask.interrupt_data.combined_total_cost || 0).toLocaleString()}</span>
                </div>

                <div className="data-row" style={{ borderTop: '1px solid var(--border)', marginTop: '4px', paddingTop: '8px' }}>
                  <span className="data-label" style={{ fontWeight: 600, color: 'var(--text-main)' }}>真实综合净毛利 (True Profit)</span>
                  <span className={`data-value ${(selectedTask.interrupt_data.true_profit || 0) < 0 ? 'danger' : 'success'}`} style={{ fontSize: '0.95rem' }}>
                    ¥{(selectedTask.interrupt_data.true_profit || 0).toLocaleString()}
                  </span>
                </div>

                <div className="data-row" style={{ alignItems: 'flex-start' }}>
                  <span className="data-label" style={{ fontWeight: 600, color: 'var(--text-main)' }}>真实综合毛利率 (True Margin)</span>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px' }}>
                      <span className={`data-value ${(selectedTask.interrupt_data.true_profit || 0) < 0 ? 'danger' : (selectedTask.interrupt_data.true_margin || 0) < 15 ? 'highlight' : 'success'}`} style={{ fontSize: '1.05rem' }}>
                        {(selectedTask.interrupt_data.true_margin || 0).toFixed(2)}%
                      </span>
                      {/* 真实风险等级徽章 */}
                      <span 
                        className="legend-pill" 
                        style={{ 
                          fontSize: '0.7rem',
                          backgroundColor: (selectedTask.interrupt_data.true_profit || 0) < 0 ? 'rgba(239, 68, 68, 0.3)' : (selectedTask.interrupt_data.true_margin || 0) < 15 ? 'rgba(245, 158, 11, 0.25)' : (selectedTask.interrupt_data.true_margin || 0) < 25 ? 'rgba(234, 179, 8, 0.25)' : 'rgba(16, 185, 129, 0.2)',
                          color: (selectedTask.interrupt_data.true_profit || 0) < 0 ? '#F87171' : (selectedTask.interrupt_data.true_margin || 0) < 15 ? '#FB923C' : (selectedTask.interrupt_data.true_margin || 0) < 25 ? '#FACC15' : '#34D399',
                          border: (selectedTask.interrupt_data.true_profit || 0) < 0 ? '1px solid #EF4444' : undefined
                        }}
                      >
                        {(selectedTask.interrupt_data.true_profit || 0) < 0 ? '🔴 极高风险 (击穿BOM)' : (selectedTask.interrupt_data.true_margin || 0) < 15 ? '🟠 偏高风险 (VP特批)' : (selectedTask.interrupt_data.true_margin || 0) < 25 ? '🟡 中度风险 (总监审批)' : '🟢 正常 (达标)'}
                      </span>
                    </div>
                    
                    {/* 标面毛利清晰解释与气泡提示 */}
                    <div style={{ marginTop: '3px' }}>
                      <span className="surface-margin-badge" title="标面毛利：未扣除赠送延保与配件赠品时的名义裸机毛利率，极易掩盖真实资损">
                        标面毛利: {(selectedTask.interrupt_data.surface_margin || 0).toFixed(1)}%
                        <span className="tooltip-hint">ℹ️ 未扣延保赠品</span>
                      </span>
                    </div>
                  </div>
                </div>

                <div className="data-row">
                  <span className="data-label">现存可用库存</span>
                  <span className="data-value" style={{ color: selectedTask.interrupt_data.stock_status === 'SHORTAGE' ? 'var(--warning)' : 'var(--success)' }}>
                    {selectedTask.interrupt_data.current_stock || 0} {selectedTask.interrupt_data.unit || '台'} 
                    {selectedTask.interrupt_data.stock_status === 'SHORTAGE' ? ` (缺口 ${selectedTask.interrupt_data.shortage_qty})` : ' (现货满足)'}
                  </span>
                </div>
              </div>

              {/* 赠品明细核算折叠卡 */}
              {selectedTask.interrupt_data.freebie_details && selectedTask.interrupt_data.freebie_details.length > 0 && (
                <div className="card" style={{ marginBottom: '1.25rem', backgroundColor: 'rgba(0,0,0,0.2)' }}>
                  <h3 style={{ fontSize: '0.825rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Package size={14} /> 赠品与配件独立核算清单
                  </h3>
                  <table className="breakdown-table">
                    <thead>
                      <tr>
                        <th>配件/礼品项目</th>
                        <th>数量</th>
                        <th>成本单价</th>
                        <th>折算总成本</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedTask.interrupt_data.freebie_details.map((item, idx) => (
                        <tr key={idx}>
                          <td>{item.name}</td>
                          <td>{item.quantity}</td>
                          <td>¥{item.unit_cost}</td>
                          <td style={{ color: '#FBBF24', fontWeight: 500 }}>¥{item.total_cost}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* 主管决策选项卡: 同意放行 VS 驳回修改 */}
              <div className="decision-tabs">
                <button 
                  type="button" 
                  className={`decision-tab ${decisionTab === 'approve' ? 'active-approve' : ''}`}
                  onClick={() => setDecisionTab('approve')}
                >
                  <ThumbsUp size={15} /> 同意特批放行
                </button>
                <button 
                  type="button" 
                  className={`decision-tab ${decisionTab === 'reject' ? 'active-reject' : ''}`}
                  onClick={() => setDecisionTab('reject')}
                >
                  <ThumbsDown size={15} /> 驳回要求销售修改
                </button>
              </div>

              {decisionTab === 'approve' ? (
                /* 同意放行表单 */
                <div>
                  <div className="form-group">
                    <label>调整/核准最终折扣 (0.50 - 1.00)</label>
                    <input 
                      type="text" 
                      value={approvedDiscountStr} 
                      onChange={e => {
                        setApprovedDiscountStr(e.target.value);
                        const num = parseFloat(e.target.value);
                        if (!isNaN(num) && num >= 0.5 && num <= 1.0) {
                          setApprovedDiscount(num);
                        }
                      }}
                      onBlur={() => {
                        let num = parseFloat(approvedDiscountStr);
                        if (isNaN(num) || num < 0.5) num = 0.5;
                        else if (num > 1.0) num = 1.0;
                        num = Math.round(num * 100) / 100;
                        setApprovedDiscount(num);
                        setApprovedDiscountStr(num.toString());
                      }}
                    />
                  </div>
                  <div className="form-group">
                    <label>特批放行批示附言</label>
                    <textarea 
                      value={comment} 
                      onChange={e => setComment(e.target.value)}
                      style={{ minHeight: '75px' }}
                    />
                  </div>
                </div>
              ) : (
                /* 驳回修改表单：包含主管交互式整改测算栏沙盒 */
                <div>
                  {/* ================= 主管交互式整改测算沙盒 (Deal Revision Simulator) ================= */}
                  <div className="revision-simulator">
                    <div className="simulator-header">
                      <div className="simulator-title">
                        <Sliders size={15} /> 主管协同整改测算栏 (Revision Simulator)
                      </div>
                      <span className="simulator-immutable-badge">
                        {isStockShortage ? '🔒 标的/标价/BOM为固定基准 (因短缺解锁提货量调整)' : '🔒 标的/订购量/标价/BOM为定死基准'}
                      </span>
                    </div>

                    {/* 只读定死基础要素展示 */}
                    <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)', marginBottom: '0.65rem', padding: '6px 8px', background: 'rgba(0,0,0,0.3)', borderRadius: '6px', lineHeight: '1.5' }}>
                      <div>📌 标的: <strong style={{ color: 'var(--text-main)' }}>[{selectedTask.interrupt_data.opp_id}] {selectedTask.interrupt_data.product_name}</strong> ({simQuantity} {selectedTask.interrupt_data.unit || '台'})</div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '2px' }}>
                        <span>官方单价: ¥{(selectedTask.interrupt_data.unit_price || 0).toLocaleString()}</span>
                        <span>单台BOM底价: ¥{(selectedTask.interrupt_data.cost_price || 0).toLocaleString()} (总BOM: ¥{simBomCost.toLocaleString()})</span>
                      </div>
                      <div style={{ color: simQuantity <= currentStock ? '#34D399' : '#F87171', marginTop: '2px' }}>
                        {simQuantity <= currentStock 
                          ? `✅ 现存库存满足: 可用 ${currentStock} ${selectedTask.interrupt_data.unit || '台'} ≥ 需求 ${simQuantity} ${selectedTask.interrupt_data.unit || '台'}` 
                          : `⚠️ 现存库存短缺: 可用仅 ${currentStock} ${selectedTask.interrupt_data.unit || '台'}，缺口 ${simQuantity - currentStock}`}
                      </div>
                    </div>

                    {/* 杠杆 0: 当库存不足时，允许主管修改订购数量 (只能减少不能增加) */}
                    {isStockShortage && (
                      <div className="sim-control-group">
                        <div className="sim-control-label">
                          <span style={{ color: '#FB923C' }}>⚠️ 现存库存不足：调整首期订购数量 (Target Quantity)</span>
                          <span className="value-preview">
                            {simQuantity} {selectedTask.interrupt_data.unit || '台'} (原申请: {originalSimQty}{selectedTask.interrupt_data.unit || '台'})
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                          <div className="sim-stepper">
                            <button 
                              type="button" 
                              onClick={() => {
                                const q = Math.max(1, simQuantity - 10);
                                setSimQuantity(q);
                                setSimQuantityStr(q.toString());
                              }}
                            >
                              -
                            </button>
                            <input 
                              type="text" 
                              value={simQuantityStr} 
                              onChange={e => {
                                setSimQuantityStr(e.target.value);
                                const val = parseInt(e.target.value);
                                if (!isNaN(val) && val >= 1 && val <= originalSimQty) {
                                  setSimQuantity(val);
                                }
                              }}
                              onBlur={() => {
                                let val = parseInt(simQuantityStr);
                                if (isNaN(val) || val < 1) val = 1;
                                else if (val > originalSimQty) val = originalSimQty;
                                setSimQuantity(val);
                                setSimQuantityStr(val.toString());
                              }}
                              style={{ width: '60px', textAlign: 'center' }}
                            />
                            <button 
                              type="button" 
                              disabled={simQuantity >= originalSimQty}
                              onClick={() => {
                                const q = Math.min(originalSimQty, simQuantity + 10);
                                setSimQuantity(q);
                                setSimQuantityStr(q.toString());
                              }}
                              style={{ opacity: simQuantity >= originalSimQty ? 0.35 : 1 }}
                            >
                              +
                            </button>
                          </div>
                          <button 
                            type="button" 
                            className="btn" 
                            style={{ fontSize: '0.725rem', padding: '0.35rem 0.6rem', backgroundColor: 'rgba(245, 158, 11, 0.2)', color: '#FBBF24', border: '1px solid rgba(245, 158, 11, 0.4)' }}
                            onClick={() => {
                              const q = Math.max(1, Math.min(currentStock, originalSimQty));
                              setSimQuantity(q);
                              setSimQuantityStr(q.toString());
                            }}
                          >
                            ⚡ 设为现存可用库存 ({currentStock}台)
                          </button>
                        </div>
                        <div style={{ fontSize: '0.7rem', marginTop: '4px', color: simQuantity <= currentStock ? '#34D399' : '#F87171' }}>
                          {simQuantity <= currentStock 
                            ? `🟢 调整后首期需求 (${simQuantity}台) ≤ 现存现货 (${currentStock}台)，现货充足缺口消除！` 
                            : `⚠️ 调整后仍存缺口 ${simQuantity - currentStock} 台 (可用仅 ${currentStock} 台)`}
                        </div>
                      </div>
                    )}

                    {/* 杠杆 1: 调整申请折扣 (支持任意自由打字，离开失焦时自动纠正) */}
                    <div className="sim-control-group">
                      <div className="sim-control-label">
                        <span>1. 调整要求折扣率 (Target Discount)</span>
                        <span className="value-preview">
                          {(simDiscount * 10).toFixed(1)} 折 ({(simDiscount * 100).toFixed(0)}%)
                        </span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <input 
                          type="range" 
                          min="0.5" 
                          max="1.0" 
                          step="0.01" 
                          value={simDiscount} 
                          onChange={e => {
                            const val = parseFloat(e.target.value);
                            setSimDiscount(val);
                            setSimDiscountStr(val.toString());
                          }}
                          style={{ flex: 1 }}
                        />
                        <input 
                          type="text" 
                          value={simDiscountStr} 
                          onChange={e => {
                            setSimDiscountStr(e.target.value);
                            const num = parseFloat(e.target.value);
                            if (!isNaN(num) && num >= 0.5 && num <= 1.0) {
                              setSimDiscount(num);
                            }
                          }}
                          onBlur={() => {
                            let num = parseFloat(simDiscountStr);
                            if (isNaN(num) || num < 0.5) num = 0.5;
                            else if (num > 1.0) num = 1.0;
                            num = Math.round(num * 100) / 100;
                            setSimDiscount(num);
                            setSimDiscountStr(num.toString());
                          }}
                          style={{ width: '65px', padding: '4px 6px', textAlign: 'center', fontSize: '0.8rem' }}
                        />
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                        折后合同实收: <strong style={{ color: '#FBBF24' }}>¥{simContractRevenue.toLocaleString()}</strong> 
                        (原实收: ¥{(selectedTask.interrupt_data.final_amount || 0).toLocaleString()})
                      </div>
                    </div>

                    {/* 杠杆 2: 调整附赠延保年数 */}
                    <div className="sim-control-group">
                      <div className="sim-control-label">
                        <span>2. 调整允许赠送延保年数 (Target Warranty)</span>
                        <span className="value-preview">
                          {simWarrantyYears} 年 (折合成本: ¥{simWarrantyCost.toLocaleString()})
                        </span>
                      </div>
                      <div className="sim-stepper">
                        <button type="button" onClick={() => setSimWarrantyYears(Math.max(0, simWarrantyYears - 1))}>-</button>
                        <input 
                          type="number" 
                          min="0" 
                          max="5" 
                          value={simWarrantyYears} 
                          onChange={e => setSimWarrantyYears(Math.max(0, parseInt(e.target.value) || 0))}
                        />
                        <button type="button" onClick={() => setSimWarrantyYears(simWarrantyYears + 1)}>+</button>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginLeft: '6px' }}>
                          每年单台成本 ¥{selectedTask.interrupt_data.warranty_cost_per_year || 0}
                        </span>
                      </div>
                    </div>

                    {/* 杠杆 3: 调整赠品配件数量 */}
                    {drawerFreebieList.length > 0 && (
                      <div className="sim-control-group">
                        <div className="sim-control-label">
                          <span>3. 赠品配件数量削减与调整 (Target Freebies)</span>
                          <span className="value-preview">
                            折合成本: ¥{simFreebieCost.toLocaleString()}
                          </span>
                        </div>
                        {drawerFreebieList.map((item: any, idx: number) => {
                          const curQ = simFreebieQtys[item.name] !== undefined ? simFreebieQtys[item.name] : item.quantity;
                          const step = (originalSimQty >= 50) ? 10 : 1;
                          return (
                            <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '6px', fontSize: '0.75rem' }}>
                              <span style={{ color: 'var(--text-muted)' }}>{item.name} (单价¥{item.unit_cost}):</span>
                              <div className="sim-stepper">
                                <button 
                                  type="button" 
                                  onClick={() => setSimFreebieQtys({ ...simFreebieQtys, [item.name]: Math.max(0, curQ - step) })}
                                >
                                  -
                                </button>
                                <input 
                                  type="number" 
                                  min="0" 
                                  value={curQ} 
                                  onChange={e => setSimFreebieQtys({ ...simFreebieQtys, [item.name]: Math.max(0, parseInt(e.target.value) || 0) })}
                                  style={{ width: '60px', textAlign: 'center' }}
                                />
                                <button 
                                  type="button" 
                                  onClick={() => setSimFreebieQtys({ ...simFreebieQtys, [item.name]: curQ + step })}
                                >
                                  +
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* 实时动态对比测算卡片 */}
                    <div className="sim-result-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '4px' }}>
                        <span style={{ fontSize: '0.775rem', fontWeight: 600, color: '#93C5FD' }}>
                          📊 方案整改测算对比 (Simulation Outcome)
                        </span>
                        <span 
                          className="legend-pill"
                          style={{
                            fontSize: '0.68rem',
                            backgroundColor: simRiskLevel === 'CRITICAL_LOSS' ? 'rgba(239, 68, 68, 0.3)' : simRiskLevel === 'VP_SPECIAL' ? 'rgba(245, 158, 11, 0.25)' : simRiskLevel === 'DIRECTOR_REVIEW' ? 'rgba(234, 179, 8, 0.25)' : 'rgba(16, 185, 129, 0.2)',
                            color: simRiskLevel === 'CRITICAL_LOSS' ? '#F87171' : simRiskLevel === 'VP_SPECIAL' ? '#FB923C' : simRiskLevel === 'DIRECTOR_REVIEW' ? '#FACC15' : '#34D399',
                            border: simRiskLevel === 'CRITICAL_LOSS' ? '1px solid #EF4444' : undefined
                          }}
                        >
                          {simRiskLevel === 'CRITICAL_LOSS' ? '🔴 极高风险 (击穿BOM)' : simRiskLevel === 'VP_SPECIAL' ? '🟠 偏高风险 (VP特批)' : simRiskLevel === 'DIRECTOR_REVIEW' ? '🟡 中度风险 (总监审批)' : '🟢 正常 (达标放行)'}
                        </span>
                      </div>

                      <div className="sim-comparison-grid">
                        <div className="sim-comparison-item">
                          <div style={{ color: 'var(--text-muted)' }}>综合履约总成本:</div>
                          <div style={{ fontWeight: 600, marginTop: '2px' }}>
                            ¥{simCombinedCost.toLocaleString()}
                            <span className={simCombinedCost <= (selectedTask.interrupt_data.combined_total_cost || 0) ? 'diff-tag-positive' : 'diff-tag-negative'}>
                              {simCombinedCost <= (selectedTask.interrupt_data.combined_total_cost || 0) ? '-' : '+'}¥{Math.abs(simCombinedCost - (selectedTask.interrupt_data.combined_total_cost || 0)).toLocaleString()}
                            </span>
                          </div>
                        </div>

                        <div className="sim-comparison-item">
                          <div style={{ color: 'var(--text-muted)' }}>真实综合净毛利:</div>
                          <div style={{ fontWeight: 600, marginTop: '2px', color: simTrueProfit < 0 ? '#F87171' : '#34D399' }}>
                            ¥{simTrueProfit.toLocaleString()}
                            <span className={simTrueProfit >= (selectedTask.interrupt_data.true_profit || 0) ? 'diff-tag-positive' : 'diff-tag-negative'}>
                              {simTrueProfit >= (selectedTask.interrupt_data.true_profit || 0) ? '+' : '-'}¥{Math.abs(simTrueProfit - (selectedTask.interrupt_data.true_profit || 0)).toLocaleString()}
                            </span>
                          </div>
                        </div>

                        <div className="sim-comparison-item" style={{ gridColumn: 'span 2' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ color: 'var(--text-muted)' }}>真实综合毛利率 (True Margin):</span>
                            <div>
                              <span style={{ textDecoration: 'line-through', color: 'var(--text-muted)', marginRight: '6px' }}>
                                {(selectedTask.interrupt_data.true_margin || 0).toFixed(2)}%
                              </span>
                              <strong style={{ fontSize: '0.95rem', color: simTrueMargin < 0 ? '#F87171' : simTrueMargin < 15 ? '#FB923C' : '#34D399' }}>
                                {simTrueMargin.toFixed(2)}%
                              </strong>
                              <span className={simTrueMargin >= (selectedTask.interrupt_data.true_margin || 0) ? 'diff-tag-positive' : 'diff-tag-negative'}>
                                {simTrueMargin >= (selectedTask.interrupt_data.true_margin || 0) ? '▲ +' : '▼ -'}{Math.abs(simTrueMargin - (selectedTask.interrupt_data.true_margin || 0)).toFixed(2)}%
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* 一键同步测算方案按钮 */}
                      <button 
                        type="button" 
                        className="btn"
                        style={{ 
                          width: '100%', 
                          marginTop: '0.65rem', 
                          fontSize: '0.75rem', 
                          padding: '0.45rem', 
                          backgroundColor: 'rgba(99, 102, 241, 0.25)', 
                          color: '#A5B4FC', 
                          border: '1px solid rgba(99, 102, 241, 0.45)' 
                        }}
                        onClick={applySimulationToInstructions}
                      >
                        <Calculator size={14} /> ⚡ 将此整改测算方案生成指示并填入下方
                      </button>
                    </div>
                  </div>

                  {/* 驳回意见文本框 (支持自由编辑或通过上方测算器一键填入) */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                    <label style={{ color: '#F87171', fontWeight: 600 }}>具体整改指示 (将通知销售端)</label>
                    {selectedTask.interrupt_data.recovery_suggestions?.length ? (
                      <button 
                        type="button" 
                        onClick={applyAiSuggestionToReject}
                        style={{ fontSize: '0.725rem', color: '#A5B4FC', background: 'transparent', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '3px' }}
                      >
                        <Sparkles size={12} /> 一键填入 AI 建议
                      </button>
                    ) : null}
                  </div>
                  <textarea 
                    value={rejectInstructions} 
                    onChange={e => setRejectInstructions(e.target.value)}
                    style={{ minHeight: '95px', borderColor: 'rgba(239, 68, 68, 0.4)' }}
                    placeholder="请输入对销售的具体修改要求，例如：变相让利过多！延保最多1年，壳砍半至250个，折扣不得低于9折"
                  />
                </div>
              )}
            </div>

            <div className="drawer-footer">
              {decisionTab === 'approve' ? (
                <button className="btn btn-success" style={{ width: '100%' }} onClick={handleSupervisorDecision} disabled={isResuming}>
                  {isResuming ? <RefreshCw className="spin" size={18} /> : <CheckCircle2 size={18} />}
                  {isResuming ? '正在唤醒并执行提单入库...' : '确认特批放行并完成提单'}
                </button>
              ) : (
                <button className="btn btn-reject" style={{ width: '100%' }} onClick={handleSupervisorDecision} disabled={isResuming}>
                  {isResuming ? <RefreshCw className="spin" size={18} /> : <RotateCcw size={18} />}
                  {isResuming ? '正在同步驳回指令至销售端...' : '确认驳回申请并返回销售端修改'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 销售提单合规预检弹窗 (Preflight Modal) */}
      {isPreflightModalOpen && preflightData && (
        <div className="preflight-modal-overlay">
          <div className="preflight-modal-card">
            <div className="preflight-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={20} color="#60A5FA" />
                <h3 style={{ margin: 0, fontSize: '1rem', color: '#F8FAFC' }}>
                  提单权益合规确认 [{preflightData.category_name}]
                </h3>
              </div>
              <button 
                type="button" 
                onClick={() => setIsPreflightModalOpen(false)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <div className="preflight-modal-body">
              {/* 拦截原因提醒 */}
              <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px', padding: '0.65rem 0.85rem' }}>
                <div style={{ fontSize: '0.78rem', color: '#F87171', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '4px' }}>
                  <AlertCircle size={14} /> 提单防资损前置拦截提醒：
                </div>
                {preflightData.reasons.map((r, idx) => (
                  <div key={idx} style={{ fontSize: '0.75rem', color: '#FECACA', lineHeight: '1.4' }}>
                    • {r}
                  </div>
                ))}
              </div>

              {/* 1. 延保配置卡片 (电子商品铁律) */}
              <div className="preflight-section-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ fontSize: '0.825rem', fontWeight: 600, color: '#93C5FD', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Clock size={15} /> 1. 商业延保权益确认 (强制配置)
                  </span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    电子设备按制度必须附延保
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(0,0,0,0.25)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-main)' }}>附赠延保年限：</span>
                  <div className="sim-stepper">
                    <button type="button" onClick={() => setModalWarrantyYears(Math.max(1, modalWarrantyYears - 1))}>-</button>
                    <input 
                      type="number" 
                      min="1" 
                      max="5" 
                      value={modalWarrantyYears} 
                      onChange={e => setModalWarrantyYears(Math.max(1, parseInt(e.target.value) || 1))}
                      style={{ width: '55px', textAlign: 'center' }}
                    />
                    <button type="button" onClick={() => setModalWarrantyYears(Math.min(5, modalWarrantyYears + 1))}>+</button>
                    <span style={{ fontSize: '0.75rem', color: '#FBBF24', marginLeft: '4px' }}>年</span>
                  </div>
                </div>
              </div>

              {/* 2. 赠品配件选配卡片 */}
              <div className="preflight-section-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ fontSize: '0.825rem', fontWeight: 600, color: '#A7F3D0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Gift size={15} /> 2. 赠品配件选配与核对
                  </span>
                  <span style={{ fontSize: '0.72rem', color: preflightData.freebie_type === 'none' ? '#F87171' : '#34D399' }}>
                    {preflightData.freebie_type === 'single' ? '单赠品专属规则' : preflightData.freebie_type === 'multiple' ? '多赠品可选规则' : '严格无赠品规则'}
                  </span>
                </div>

                {/* 各种情况对应渲染 */}
                {preflightData.freebie_type === 'none' ? (
                  <div style={{ padding: '0.6rem', background: 'rgba(239, 68, 68, 0.08)', borderRadius: '6px', border: '1px solid rgba(239, 68, 68, 0.25)', fontSize: '0.75rem', color: '#FCA5A5' }}>
                    ⚠️ 该商品属于 DIY 硬件散件 / 企业级设备，财务制度明确<strong>严禁附加任何赠品</strong>！即使提单口头承诺赠品也将被系统自动忽略并清零。
                  </div>
                ) : preflightData.allowed_freebies.map((f, idx) => {
                  const isChecked = modalSelectedFreebies[f.name] || false;
                  const curQty = modalFreebieQtys[f.name] ?? (preflightData.quantity || 1);
                  return (
                    <div key={idx} className={`preflight-freebie-option ${isChecked ? 'selected' : ''}`}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', flex: 1 }}>
                        <input 
                          type="checkbox" 
                          checked={isChecked}
                          onChange={e => setModalSelectedFreebies({ ...modalSelectedFreebies, [f.name]: e.target.checked })}
                          style={{ accentColor: 'var(--primary)', width: '16px', height: '16px' }}
                        />
                        <div>
                          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)' }}>{f.name}</span>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>成本单价: ¥{f.unit_cost} / 个</div>
                        </div>
                      </label>

                      {isChecked && (
                        <div className="sim-stepper">
                          <button 
                            type="button" 
                            onClick={() => setModalFreebieQtys({ ...modalFreebieQtys, [f.name]: Math.max(1, curQty - 10) })}
                          >-</button>
                          <input 
                            type="number" 
                            min="1" 
                            value={curQty} 
                            onChange={e => setModalFreebieQtys({ ...modalFreebieQtys, [f.name]: Math.max(1, parseInt(e.target.value) || 1) })}
                            style={{ width: '60px', textAlign: 'center' }}
                          />
                          <button 
                            type="button" 
                            onClick={() => setModalFreebieQtys({ ...modalFreebieQtys, [f.name]: curQty + 10 })}
                          >+</button>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>个</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="preflight-modal-footer">
              <button 
                type="button" 
                className="btn" 
                style={{ backgroundColor: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)' }}
                onClick={() => setIsPreflightModalOpen(false)}
              >
                取消
              </button>
              <button 
                type="button" 
                className="btn btn-primary"
                onClick={confirmPreflightAndSubmit}
              >
                <CheckCircle2 size={16} /> 确认并更新提单提交
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
