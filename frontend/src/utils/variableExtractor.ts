import type { VariableInfo, BlockData, GlobalVariableItem, VariableOccurrence } from '../types';

/**
 * Common standard symbols and their canonical academic meanings as universal baseline.
 */
const CANONICAL_SYMBOLS: Record<string, { name: string; desc: string }> = {
  'Q': { name: 'Query Matrix (查询矩阵 $Q$)', desc: '当前序列待查询位置的特征表示矩阵，用于计算注意力匹配得分' },
  'K': { name: 'Key Matrix (键矩阵 $K$)', desc: '上下文序列的键特征表示矩阵，与查询向量计算相关度兼容性' },
  'V': { name: 'Value Matrix (值矩阵 $V$)', desc: '待加权聚合的内容表征向量矩阵，按注意力权重线性加权求和输出' },
  'd_k': { name: 'Key/Query Dimension (键/查询维度 $d_k$)', desc: '键与查询向量的特征维度，在注意力缩放因子中作为 $\\sqrt{d_k}$ 缩放除数' },
  'd_v': { name: 'Value Dimension (值维度 $d_v$)', desc: '值向量的内容表征维度，决定每个注意力头输出的向量长度' },
  'd_{model}': { name: 'Model Dimension (模型嵌入维度 $d_{\\text{model}}$)', desc: '网络全架构隐藏层统一嵌入特征维度（如 512 或 768）' },
  'd_{\\text{model}}': { name: 'Model Dimension (模型嵌入维度 $d_{\\text{model}}$)', desc: '网络全架构隐藏层统一嵌入特征维度（如 512 或 768）' },
  'd_{\\mathrm{model}}': { name: 'Model Dimension (模型嵌入维度 $d_{\\text{model}}$)', desc: '网络全架构隐藏层统一嵌入特征维度（如 512 或 768）' },
  'd_{ff}': { name: 'Feed-Forward Dimension (前馈隐藏层维度 $d_{ff}$)', desc: '逐位置前馈神经网络内部中间膨胀维度，通常为 $4 \\times d_{\\text{model}}$' },
  'W^O': { name: 'Output Projection (多头输出投影矩阵 $W^O$)', desc: '将所有并行注意力头拼接后的高维向量投影回模型维度的参数矩阵' },
  'W_i^Q': { name: 'Query Projection (第 $i$ 头查询投影 $W_i^Q$)', desc: '将输入查询投影至第 $i$ 个注意力子空间的权重矩阵' },
  'W_i^K': { name: 'Key Projection (第 $i$ 头键投影 $W_i^K$)', desc: '将输入键投影至第 $i$ 个注意力子空间的权重矩阵' },
  'W_i^V': { name: 'Value Projection (第 $i$ 头值投影 $W_i^V$)', desc: '将输入值投影至第 $i$ 个注意力子空间的权重矩阵' },
  'W_1': { name: 'FFN Weight 1 (前馈层第 1 层权重 $W_1$)', desc: '前馈神经网络第一层线性变换参数矩阵' },
  'W_2': { name: 'FFN Weight 2 (前馈层第 2 层权重 $W_2$)', desc: '前馈神经网络第二层线性变换参数矩阵' },
  'b_1': { name: 'FFN Bias 1 (前馈层第 1 层偏置 $b_1$)', desc: '前馈网络第一层可学习偏置向量' },
  'b_2': { name: 'FFN Bias 2 (前馈层第 2 层偏置 $b_2$)', desc: '前馈网络第二层可学习偏置向量' },
  'PE': { name: 'Positional Encoding (位置编码 $PE$)', desc: '基于正余弦函数或可学习向量为输入注入序列绝对或相对位置信息 ($PE$)' },
  'P': { name: 'Probability / Projection Matrix (概率/投影矩阵 $P$)', desc: '概率分布状态矩阵或线性投影变换表示 ($P$)' },
  'x': { name: 'Input Representation (输入表征向量 $x$)', desc: '输入序列特征表示向量或神经网络激活输入' },
  'z': { name: 'Latent Representation (连续隐层状态 $z$)', desc: '编码器输出的中间连续表示向量序列' },
  'y': { name: 'Target Sequence (目标输出序列 $y$)', desc: '解码器生成或待预测的目标标记序列' },
  'pos': { name: 'Sequence Position (序列位置 $pos$)', desc: 'Token 标记在输入序列中的离散时间步或位置索引' },
  'i': { name: 'Dimension Index (维度索引 $i$)', desc: '向量特征维度上的分量索引，范围为 $0 \\le i < d_{\\text{model}}/2$' },
  'h': { name: 'Attention Heads (并行注意力头数 $h$)', desc: '多头注意力机制中并行运行的注意力头总数（如 8 或 16）' },
  'N': { name: 'Layer Count (网络堆叠层数 $N$)', desc: '编码器与解码器中同构子层的堆叠重复次数（如 6 或 12）' },
  '\\beta_1': { name: 'Adam Beta 1 (一阶动量衰减系数 $\\beta_1$)', desc: 'Adam 优化器中梯度一阶矩估计的指数衰减率（通常设为 0.9）' },
  '\\beta_2': { name: 'Adam Beta 2 (二阶动量衰减系数 $\\beta_2$)', desc: 'Adam 优化器中未中心化二阶矩估计的指数衰减率（通常设为 0.98 或 0.999）' },
  '\\epsilon': { name: 'Epsilon (数值稳定微小常数 $\\epsilon$)', desc: '防止除以零的数值稳定极小量，通常设为 $10^{-9}$' },
  'head_i': { name: 'Attention Head i (第 $i$ 注意力头 $\\text{head}_i$)', desc: '第 $i$ 个并行注意力子空间的映射与注意力表征计算结果' },
  'head_{i}': { name: 'Attention Head i (第 $i$ 注意力头 $\\text{head}_i$)', desc: '第 $i$ 个并行注意力子空间的映射与注意力表征计算结果' },
  'step_num': { name: 'Step Number (当前训练步数 $\\text{step\\_num}$)', desc: '模型当前优化迭代的总训练步数' },
  'step\\_num': { name: 'Step Number (当前训练步数 $\\text{step\\_num}$)', desc: '模型当前优化迭代的总训练步数' },
  'warmup_steps': { name: 'Warmup Steps (预热步数 $\\text{warmup\\_steps}$)', desc: '学习率线性上升的初始预热步数（如 4000 步）' },
  'warmup\\_steps': { name: 'Warmup Steps (预热步数 $\\text{warmup\\_steps}$)', desc: '学习率线性上升的初始预热步数（如 4000 步）' },
  'lrate': { name: 'Learning Rate (动态学习率 $\\text{lrate}$)', desc: '根据步数与预热衰减策略动态调度的当前优化器学习率' },
};

/**
 * Extracts symbols and contextual explanations for mathematical expressions.
 */
export function extractFormulaVariables(
  latex: string,
  contextEn: string = '',
  contextZh: string = ''
): VariableInfo[] {
  if (!latex) return [];

  const foundSymbols: Set<string> = new Set();
  const cleanedLatex = latex
    .replace(/\\mathrm\{([A-Za-z0-9_]+)\}/g, '$1')
    .replace(/\\text\{([A-Za-z0-9_]+)\}/g, '$1');

  // Candidate variable patterns (prioritize multi-char tokens like PE before single capital letters)
  const candidatePatterns = [
    /\b(PE|Q|K|V|W\^[A-Za-z0-9]+|W_[A-Za-z0-9^]+|d_k|d_v|d_\{model\}|d_\{ff\}|pos|head_i|head_\{i\}|step_num|warmup_steps|lrate)\b/g,
    /\\(beta_1|beta_2|epsilon|alpha|lambda|sigma|theta|gamma|mu)/g,
    /\b([A-Z])\b/g,
  ];

  for (const pat of candidatePatterns) {
    const matches = cleanedLatex.match(pat);
    if (matches) {
      for (const m of matches) {
        if (!['A', 'I', 'O', 'T', 'EXP', 'LOG', 'SIN', 'COS', 'MAX', 'MIN'].includes(m.toUpperCase())) {
          foundSymbols.add(m);
        } else if (['Q', 'K', 'V', 'N', 'P'].includes(m)) {
          foundSymbols.add(m);
        }
      }
    }
  }

  // Also check direct canonical symbols
  for (const sym of Object.keys(CANONICAL_SYMBOLS)) {
    const normSym = sym.replace(/[\\]/g, '');
    if (latex.includes(sym) || cleanedLatex.includes(normSym)) {
      foundSymbols.add(sym);
    }
  }

  const results: VariableInfo[] = [];
  const combinedContext = `${contextEn}\n${contextZh}`;

  for (const sym of foundSymbols) {
    let name = '';
    let desc = '';

    // Check canonical knowledge base first
    const canonical = CANONICAL_SYMBOLS[sym] || CANONICAL_SYMBOLS[sym.replace(/[\\]/g, '')];
    if (canonical) {
      name = canonical.name;
      desc = canonical.desc;
    }

    // Attempt contextual pattern matching in paper text
    // e.g. "where d_k represents ..." or "packed together into a matrix Q"
    const escapedSym = sym.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const contextRegex = new RegExp(
      `(?:where|with|wherein|denote|representing|packing)\\s+[^.\\n]*?\\$?${escapedSym}\\$?` +
      `\\s*(?:is|are|=|represents?|denotes?|refers?\\s+to|indicates?|dimensions?)\\s+([^,.;\\n]{5,100})`,
      'i'
    );
    const mCtx = combinedContext.match(contextRegex);
    if (mCtx && mCtx[1]) {
      const dynamicDesc = mCtx[1].trim();
      desc = dynamicDesc.length > 5 ? `${dynamicDesc} (${desc})` : desc;
    }

    // Chinese contextual check: e.g. "其中 Q 表示查询..."
    const zhRegex = new RegExp(`(?:其中|这里)\\s*[^。\\n]*?${escapedSym}\\s*(?:表示|为|代表|是)\\s*([^，。\\n]{3,60})`, 'i');
    const mZh = combinedContext.match(zhRegex);
    if (mZh && mZh[1]) {
      name = `${sym}: ${mZh[1].trim()}`;
    }

    if (!name) {
      name = `数学符号 $${sym}$`;
    }

    results.push({
      symbol: sym.startsWith('$') ? sym : `$${sym}$`,
      name,
      desc: desc || `公式中的关键数学变量或超参数（$${sym}$）`,
    });
  }

  // Deduplicate by symbol name
  const uniqueMap = new Map<string, VariableInfo>();
  for (const item of results) {
    const key = item.symbol.toLowerCase();
    if (!uniqueMap.has(key)) {
      uniqueMap.set(key, item);
    }
  }

  return Array.from(uniqueMap.values()).slice(0, 8);
}

/**
 * Builds a paper-wide global variable index aggregating all formula symbols,
 * their contextual meanings, and occurrences across pages and equations.
 */
export function buildGlobalVariableIndex(blocks: BlockData[]): GlobalVariableItem[] {
  if (!blocks || blocks.length === 0) return [];

  const globalMap = new Map<string, GlobalVariableItem>();

  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (b.type !== 'equation' || !b.en) continue;

    // Surrounding context
    const prev = i > 0 ? blocks[i - 1] : undefined;
    const next = i < blocks.length - 1 ? blocks[i + 1] : undefined;
    const contextEn = `${prev?.en || ''} ${next?.en || ''}`;
    const contextZh = `${prev?.zh || ''} ${next?.zh || ''}`;

    const vars = extractFormulaVariables(b.en, contextEn, contextZh);
    const occurrence: VariableOccurrence = {
      page: b.page,
      blockIdx: b.idx,
      formulaLatex: b.en,
    };

    for (const v of vars) {
      const cleanSymbol = v.symbol.replace(/^\$|\$$/g, '').trim();
      const key = cleanSymbol.toLowerCase();

      if (globalMap.has(key)) {
        const item = globalMap.get(key)!;
        item.count += 1;
        // Avoid duplicate occurrence on the same block
        if (!item.occurrences.some(o => o.page === occurrence.page && o.blockIdx === occurrence.blockIdx)) {
          item.occurrences.push(occurrence);
        }
        // If current desc is richer than baseline, update desc
        if (v.desc && v.desc.length > item.desc.length && !item.desc.includes('(')) {
          item.desc = v.desc;
        }
        if (v.name && !item.name.includes(':') && v.name.includes(':')) {
          item.name = v.name;
        }
      } else {
        globalMap.set(key, {
          symbol: v.symbol,
          cleanSymbol,
          name: v.name,
          desc: v.desc,
          occurrences: [occurrence],
          count: 1,
        });
      }
    }
  }

  // Sort by count descending, then by first occurrence
  return Array.from(globalMap.values()).sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    const firstA = a.occurrences[0];
    const firstB = b.occurrences[0];
    if (firstA && firstB) {
      if (firstA.page !== firstB.page) return firstA.page - firstB.page;
      return firstA.blockIdx - firstB.blockIdx;
    }
    return 0;
  });
}

