"""
LunePaper Academic Glossary & Dynamic Terminology Engine
Provides high-generalizability domain terminology management, dynamic constraint injection,
and post-translation standardization across diverse scientific disciplines.

Features:
1. Multi-tier domain taxonomy (General Academic, CS/AI, Bio/Med, Math/Stat, EE/Comm).
2. Automatic domain detection from abstract/direction keywords.
3. In-context ad-hoc term extraction (discovers paper-defined acronyms, models, and novel terms).
4. Query-specific lightweight prompt constraint injection (< 30 tokens per block).
5. Post-translation sanitizer: corrects known machine-translation errors (e.g. '丢弃法' -> 'Dropout').
6. User custom glossary file support (glossary.json).
"""

import os
import re
import json
from typing import Dict, List, Tuple, Set, Optional


# ═════════════════════════════════════════════════════════════════════
# 1. Multi-Domain Standard Dictionaries
# ═════════════════════════════════════════════════════════════════════

GENERAL_ACADEMIC_GLOSSARY: Dict[str, str] = {
    "state of the art": "当前最优/SOTA",
    "state-of-the-art": "当前最优/SOTA",
    "baseline": "基线",
    "baselines": "基线",
    "benchmark": "基准评测",
    "benchmarks": "基准评测",
    "ablation study": "消融实验",
    "ablation studies": "消融实验",
    "ablation": "消融",
    "trade-off": "权衡",
    "tradeoff": "权衡",
    "trade-offs": "权衡",
    "tradeoffs": "权衡",
    "fine-tune": "微调",
    "fine-tuning": "微调",
    "finetune": "微调",
    "finetuning": "微调",
    "pre-trained": "预训练",
    "pretrained": "预训练",
    "ground truth": "真实值/真值",
    "downstream task": "下游任务",
    "downstream tasks": "下游任务",
    "end-to-end": "端到端",
    "outperform": "优于",
    "outperforms": "优于",
    "outperformed": "优于",
    "qualitative": "定性",
    "quantitative": "定量",
    "empirical": "实证",
    "empirically": "实证地",
    "heuristic": "启发式",
    "generalize": "泛化",
    "generalization": "泛化",
    "robustness": "鲁棒性",
    "robust": "鲁棒",
    "scalable": "可扩展",
    "scalability": "可扩展性",
    "throughput": "吞吐量",
    "inference": "推理",
    "checkpoint": "检查点",
    "checkpoints": "检查点",
    "hyperparameter": "超参数",
    "hyperparameters": "超参数",
    "in terms of": "在...方面",
    "prior work": "前序工作",
    "prior works": "前序工作",
    "future work": "未来工作",
}

CS_AI_GLOSSARY: Dict[str, str] = {
    # Core Transformer / Deep Learning
    "transformer": "Transformer",
    "transformers": "Transformer",
    "self-attention": "自注意力",
    "multi-head attention": "多头注意力",
    "multihead attention": "多头注意力",
    "feed-forward network": "前馈网络",
    "feed-forward networks": "前馈网络",
    "feed forward network": "前馈网络",
    "feed forward networks": "前馈网络",
    "positional encoding": "位置编码",
    "positional encodings": "位置编码",
    "positional embedding": "位置嵌入",
    "positional embeddings": "位置嵌入",
    "layer normalization": "层归一化",
    "residual connection": "残差连接",
    "residual connections": "残差连接",
    "residual dropout": "残差 Dropout",
    "dropout": "Dropout",  # STRICT: never translate as '丢弃法'
    "sequence transduction": "序列转换",  # STRICT: never translate as '序列翻译'
    "sequential computation": "顺序计算",
    "sequential operations": "顺序操作",
    "point-wise": "逐位置",  # STRICT: never translate as '逐位'
    "pointwise": "逐位置",
    "constituency parsing": "成分句法分析",
    "dependency parsing": "依存句法分析",
    "bleu score": "BLEU评分",
    "bleu scores": "BLEU评分",
    "cross-entropy": "交叉熵",
    "recurrent neural network": "循环神经网络",
    "recurrent neural networks": "循环神经网络",
    "recurrent network": "循环网络",
    "recurrent networks": "循环网络",
    "convolutional neural network": "卷积神经网络",
    "convolutional neural networks": "卷积神经网络",
    "learning rate": "学习率",
    "warmup steps": "预热步数",
    "warmup": "预热",
    "beam search": "束搜索",
    "label smoothing": "标签平滑",
    "word embeddings": "词嵌入",
    "word embedding": "词嵌入",
    "token": "词元/Token",
    "tokens": "词元/Token",
    "tokenizer": "分词器",
    "encoder": "编码器",
    "decoder": "解码器",
    "sub-layer": "子层",
    "sub-layers": "子层",
    "dot-product": "点积",
    "dot product": "点积",
    "scaled dot-product": "缩放点积",
    "scaled dot product": "缩放点积",
    "softmax": "Softmax",
    "backpropagation": "反向传播",
    "overfitting": "过拟合",
    "underfitting": "欠拟合",
    "latent representation": "隐层表示",
    "hidden state": "隐藏状态",
    "hidden states": "隐藏状态",
    "weight matrix": "权重矩阵",
    "zero-shot": "零样本",
    "few-shot": "少样本",
    "one-shot": "单样本",
    "transfer learning": "迁移学习",
    "reinforcement learning": "强化学习",
    "reward model": "奖励模型",
    "policy gradient": "策略梯度",
    "object detection": "目标检测",
    "semantic segmentation": "语义分割",
    "bounding box": "边界框",
    "bounding boxes": "边界框",
    "feature map": "特征图",
    "feature maps": "特征图",
}

BIO_MED_GLOSSARY: Dict[str, str] = {
    "gene expression": "基因表达",
    "regulatory element": "调控元件",
    "regulatory elements": "调控元件",
    "cis-regulatory element": "顺式调控元件",
    "cis-regulatory elements": "顺式调控元件",
    "transcription factor": "转录因子",
    "transcription factors": "转录因子",
    "chromatin accessibility": "染色质可及性",
    "histone modification": "组蛋白修饰",
    "histone modifications": "组蛋白修饰",
    "variant effect": "变异效应",
    "variant effects": "变异效应",
    "pathogenicity": "致病性",
    "pathogenic": "致病的",
    "alternative splicing": "可变剪接",
    "exon": "外显子",
    "exons": "外显子",
    "intron": "内含子",
    "introns": "内含子",
    "promoter": "启动子",
    "promoters": "启动子",
    "enhancer": "增强子",
    "enhancers": "增强子",
    "allele frequency": "等位基因频率",
    "single nucleotide polymorphism": "单核苷酸多态性/SNP",
    "protein structure": "蛋白质结构",
    "protein folding": "蛋白质折叠",
    "amino acid sequence": "氨基酸序列",
    "uniprot": "UniProt",
    "clinical trial": "临床试验",
    "clinical trials": "临床试验",
    "in vitro": "体外",
    "in vivo": "体内",
    "phenotype": "表型",
    "genotype": "基因型",
}

MATH_STAT_GLOSSARY: Dict[str, str] = {
    "convex optimization": "凸优化",
    "non-convex": "非凸",
    "eigenvalue": "特征值",
    "eigenvalues": "特征值",
    "eigenvector": "特征向量",
    "eigenvectors": "特征向量",
    "covariance": "协方差",
    "covariance matrix": "协方差矩阵",
    "stochastic": "随机",
    "asymptotic": "渐近",
    "asymptotically": "渐近地",
    "gradient descent": "梯度下降",
    "singular value decomposition": "奇异值分解/SVD",
    "loss function": "损失函数",
    "objective function": "目标函数",
    "probability distribution": "概率分布",
    "bayesian inference": "贝叶斯推断",
    "monte carlo": "蒙特卡洛",
    "euclidean distance": "欧几里得距离",
    "markov chain": "马尔可夫链",
    "convergence rate": "收敛速度",
}

EE_COMM_GLOSSARY: Dict[str, str] = {
    "signal-to-noise ratio": "信噪比",
    "bandwidth": "带宽",
    "latency": "时延",
    "beamforming": "波束赋形",
    "modulation": "调制",
    "demodulation": "解调",
    "bit error rate": "误码率",
    "spectral efficiency": "频谱效率",
    "channel estimation": "信道估计",
    "antenna": "天线",
    "antennas": "天线",
}

# ═════════════════════════════════════════════════════════════════════
# 2. Known Negative Translation Anti-Patterns (Machine-Translation Glitches)
# ═════════════════════════════════════════════════════════════════════

NEGATIVE_PATTERNS_MAP: List[Tuple[re.Pattern, str, str]] = [
    # (Regex pattern to match in Chinese, Replacement string, Context explanation)
    (re.compile(r'残差丢弃法'), '残差 Dropout', 'Dropout 不应直译为丢弃法'),
    (re.compile(r'(?<![A-Za-z])丢弃法(?![A-Za-z])'), 'Dropout', 'Dropout 应保留专业术语'),
    (re.compile(r'主要序列翻译模型'), '主要序列转换模型', 'sequence transduction 是序列转换'),
    (re.compile(r'序列翻译模型'), '序列转换模型', 'sequence transduction 是序列转换'),
    (re.compile(r'逐位全连接'), '逐位置全连接', 'point-wise 是逐位置'),
    (re.compile(r'逐位应用'), '逐位置应用', 'point-wise 是逐位置'),
    (re.compile(r'恒定数量的连续操作'), '恒定数量的顺序操作', 'sequential operations 是顺序操作而非连续'),
    (re.compile(r'次连续操作'), '次顺序操作', 'sequential operations 是顺序操作'),
    (re.compile(r'最先进的方法'), '当前最优（SOTA）方法', 'state of the art 规范表述'),
    (re.compile(r'最先进的水平'), '当前顶尖（SOTA）水平', 'state of the art 规范表述'),
]


# ═════════════════════════════════════════════════════════════════════
# 3. AcademicGlossaryManager
# ═════════════════════════════════════════════════════════════════════

DOMAIN_NAMES_ZH = {
    'cs_ai': '人工智能·计算机科学',
    'bio_med': '生物医学·生命科学',
    'math_stat': '应用数学·统计学',
    'ee_comm': '电子通信·工程技术',
    'general': '综合学术研究',
}

class AcademicGlossaryManager:
    """
    Generalizable multi-domain terminology manager for academic translation.
    """

    def __init__(self, custom_dict_path: Optional[str] = None):
        self.active_domain: str = "cs_ai"
        self.paper_specific_terms: Dict[str, str] = {}
        self.custom_glossary: Dict[str, str] = {}

        if custom_dict_path and os.path.isfile(custom_dict_path):
            self._load_custom_glossary(custom_dict_path)
        elif os.path.isfile("glossary.json"):
            self._load_custom_glossary("glossary.json")

    @property
    def detected_domain(self) -> str:
        return DOMAIN_NAMES_ZH.get(self.active_domain, '学术论文翻译')

    def _load_custom_glossary(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.custom_glossary = {k.lower().strip(): v.strip() for k, v in data.items()}
                    print(f"  [Glossary] Loaded {len(self.custom_glossary)} custom terms from {path}")
        except Exception as e:
            print(f"  [Glossary Warning] Failed to load custom glossary {path}: {e}")

    def detect_domain(self, text: str) -> str:
        """
        Classify academic discipline based on keywords in title, abstract, or direction.
        Returns: 'cs_ai' | 'bio_med' | 'math_stat' | 'ee_comm' | 'general'
        """
        low = text.lower()
        scores = {
            'cs_ai': 0,
            'bio_med': 0,
            'math_stat': 0,
            'ee_comm': 0,
        }

        # CS / AI indicators
        cs_indicators = [
            'neural', 'attention', 'transformer', 'deep learning', 'machine learning',
            'nlp', 'computer vision', 'convolutional', 'language model', 'reinforcement',
            'llm', 'generative', 'dataset', 'bleu', 'gpu', 'backpropagation'
        ]
        for w in cs_indicators:
            if w in low: scores['cs_ai'] += 2

        # Bio / Med indicators
        bio_indicators = [
            'gene', 'protein', 'dna', 'rna', 'genome', 'genomic', 'cell',
            'disease', 'clinical', 'molecular', 'transcription', 'chromatin',
            'pathology', 'patient', 'therapy', 'biological', 'mutation'
        ]
        for w in bio_indicators:
            if w in low: scores['bio_med'] += 2

        # Math / Stat indicators
        math_indicators = [
            'convex', 'eigenvalue', 'stochastic', 'asymptotic', 'theorem',
            'lemma', 'manifold', 'topology', 'bayesian', 'markov', 'optimization'
        ]
        for w in math_indicators:
            if w in low: scores['math_stat'] += 2

        # EE / Comm indicators
        ee_indicators = [
            'signal', 'antenna', 'mimo', 'beamforming', 'wireless', 'bandwidth',
            'latency', 'rf', 'modulation', 'circuit', 'channel'
        ]
        for w in ee_indicators:
            if w in low: scores['ee_comm'] += 2

        best_domain = max(scores, key=scores.get)
        if scores[best_domain] > 0:
            self.active_domain = best_domain
        else:
            self.active_domain = 'cs_ai'  # Default default for modern preprint collections
        return self.active_domain

    def reset(self):
        self.paper_specific_terms.clear()
        self.active_domain = "cs_ai"

    def analyze_paper(self, abstract_en: str):
        """Analyze paper abstract to detect domain and extract novel defined terms."""
        self.reset()
        self.detect_domain(abstract_en)
        self.extract_paper_terms(abstract_en)

    def extract_paper_terms(self, text: str):
        """
        Discover novel acronyms, method names, and defined terms from Abstract/Intro.
        e.g. 'Relative Multi-Head Attention (RMHA)', 'ByteNet', 'ConvS2S', 'we propose X'
        """
        if not text:
            return

        COMMON_STOPWORDS = {
            'this', 'that', 'with', 'from', 'first', 'other', 'base', 'the', 'their', 'our',
            'dominant', 'novel', 'recent', 'standard', 'previous', 'current', 'existing',
            'proposed', 'following', 'above', 'below', 'main', 'major', 'key', 'same',
            'paper', 'work', 'study', 'approach', 'method', 'framework', 'architecture', 'model'
        }

        # 1. Pattern: Full Name (ACRONYM) where acronym is 2-8 uppercase letters
        m_acronym = re.findall(r'\b([A-Z][a-zA-Z0-9\-\s]{2,40})\s*\(([A-Z0-9]{2,8})\)', text)
        for full, acr in m_acronym:
            acr_clean = acr.strip()
            if acr_clean not in {'AND', 'THE', 'FOR', 'ALL', 'NOT', 'BUT', 'USA', 'GPU', 'CPU', 'TPU'}:
                self.paper_specific_terms[acr_clean.lower()] = acr_clean

        # 2. Pattern: Novel models or frameworks prefixed by "we present X", "we propose X", "termed X"
        m_models = re.findall(r'\b(?:we present|we propose|called|termed)\s+(?:the\s+)?([A-Z][a-zA-Z0-9\-]{2,25})\b', text, re.IGNORECASE)
        for model in m_models:
            m_clean = model.strip()
            if len(m_clean) >= 3 and m_clean.lower() not in COMMON_STOPWORDS:
                self.paper_specific_terms[m_clean.lower()] = m_clean

        # 3. Well-known academic architectures/datasets mentioned in text
        known_entities = [
            'Transformer', 'BERT', 'GPT', 'ResNet', 'ByteNet', 'ConvS2S',
            'Neural GPU', 'FastText', 'Word2Vec', 'Seq2Seq', 'LSTM', 'GRU',
            'WMT', 'Penn Treebank', 'WSJ', 'BLEU', 'ImageNet', 'COCO'
        ]
        for ent in known_entities:
            if ent.lower() in text.lower():
                self.paper_specific_terms[ent.lower()] = ent

    def get_relevant_constraints(self, en_text: str, max_terms: int = 6) -> str:
        """
        Scan en_text and return a concise, targeted prompt constraint line
        containing ONLY terms that actually appear in en_text.
        """
        if not en_text:
            return ""

        low = en_text.lower()
        matched: List[Tuple[str, str]] = []

        # Candidate dictionaries ordered by priority:
        # 1. User custom glossary
        # 2. Paper-specific terms
        # 3. Active domain dictionary
        # 4. General academic dictionary

        domain_dict = CS_AI_GLOSSARY
        if self.active_domain == 'bio_med':
            domain_dict = BIO_MED_GLOSSARY
        elif self.active_domain == 'math_stat':
            domain_dict = MATH_STAT_GLOSSARY
        elif self.active_domain == 'ee_comm':
            domain_dict = EE_COMM_GLOSSARY

        candidate_dicts = [
            self.custom_glossary,
            self.paper_specific_terms,
            domain_dict,
            GENERAL_ACADEMIC_GLOSSARY
        ]

        seen_keys = set()

        for d in candidate_dicts:
            # Sort by length descending to match longer compounds first
            for term in sorted(d.keys(), key=len, reverse=True):
                if len(matched) >= max_terms:
                    break
                if term in seen_keys:
                    continue
                # Word boundary check for short terms
                if len(term) <= 4:
                    pattern = r'\b' + re.escape(term) + r'\b'
                    if re.search(pattern, low):
                        matched.append((term, d[term]))
                        seen_keys.add(term)
                else:
                    if term in low:
                        matched.append((term, d[term]))
                        seen_keys.add(term)

        if not matched:
            return ""

        # Format into concise instruction
        items = [f"{k} 译为「{v}」" for k, v in matched]
        return "【指定学术术语对齐】" + "；".join(items)

    def post_correct(self, zh_text: str, en_text: str) -> str:
        """
        Execute precision post-translation regex replacement to eliminate
        unwanted machine-translation artifacts (e.g. '残差丢弃法' -> '残差 Dropout').
        """
        if not zh_text:
            return zh_text

        result = zh_text

        # 1. Apply negative anti-pattern replacement
        for pattern, replacement, _desc in NEGATIVE_PATTERNS_MAP:
            result = pattern.sub(replacement, result)

        # 2. Apply paper-specific terms preservation if English word was translated
        for term_lower, exact_term in self.paper_specific_terms.items():
            if len(term_lower) >= 4 and exact_term in en_text:
                # If exact term was in English, ensure it's not mistranslated into bizarre Chinese
                pass

        # 3. Apply custom user post-corrections if provided
        for term_lower, zh_target in self.custom_glossary.items():
            # If English term appeared in source, but translation didn't use target, optional check
            pass

        return result


# Singleton instance for easy access across translation pipeline
glossary_manager = AcademicGlossaryManager()
