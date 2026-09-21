/**
 * Utility to accurately detect and format code, pseudocode, and algorithm blocks in academic papers.
 */

// Regex patterns for explicit code construct indicators
const CODE_START_PATTERNS = [
  /^\s*(?:def|function)\s+[a-zA-Z0-9_]+\s*\(/m,
  /^\s*class\s+[a-zA-Z0-9_]+(?:\([^)]*\))?\s*:/m,
  /^\s*from\s+[a-zA-Z0-9_.]+\s+import\s+[a-zA-Z0-9_*]/m,
  /^\s*import\s+[a-zA-Z0-9_.]+(?:\s+as\s+[a-zA-Z0-9_]+)?\s*$/m,
  /^\s*(?:procedure|algorithm)\s+[a-zA-Z0-9_]+\s*\(/im,
  /^\s*Algorithm\s+\d+\b/m,
  /^\s*(?:void|int|float|double|bool|const|let|var)\s+[a-zA-Z0-9_]+\s*=/m,
  /^\s*(?:Input\s*:|Output\s*:|Require\s*:|Ensure\s*:|Initialization\s*:|Parameters\s*:|State\s*:)/im,
  /^\s*(?:system_prompt|user_prompt|assistant_prompt|diversity_user_prompt|task_description|Finish_function_description)\s*:/im,
  /^\s*(?:\{\s*"?|\},\s*\{|\[\s*\{|\}\s*\])/,
  /^\s*"(?:name|type|description|parameters|properties|tool_description|api_list|url|default|Query|related_apis|api_name)"\s*:\s*/m,
  /\{[a-zA-Z0-9_]*(?:task|candidate|description|instruction|query|input|output|prompt|state)[a-zA-Z0-9_]*\}/,
];

const CODE_KEYWORD_PATTERNS = [
  /\b(?:torch|nn|np|cuda|rearrange|masked_fill|new_zeros|zeros_like|cumsum|arange|triu|tril)\b/,
  /^\s*for\s+\w+\s+in\s+range\b/m,
  /^\s*(?:if\s+|elif\s+|else:|return\s+|while\s+|lambda\s+)/m,
  /\[\s*:\s*,\s*:\s*,\s*[^\]]+\]/, // Tensor slicing like [:, :, i, None]
  /\b(?:int|float|bool|str|torch\.Tensor|Optional\[)\b/,
  /^\s*(?:for\s+each|foreach)\b[^\n]+?\bdo(?:\s*$|\s+)/im,
  /^\s*while\b[^\n]+?\bdo(?:\s*$|\s+)/im,
  /^\s*for\b[^\n]+?\bdo(?:\s*$|\s+)/im,
  /^\s*if\b[^\n]+?\bthen(?:\s*$|\s+)/im,
  /^\s*(?:repeat|until\b[^\n]+|end\s+(?:while|for|if|procedure)\b)/im,
  /^[a-zA-Z0-9_]\s*(?::=|←|\\leftarrow|\\Leftarrow)\s*/m,
  /\b(?:argmax|argmin|softmax|len\(|append\(|pop\(|push\(|sort\(|split\()\b/,
];

/**
 * Checks whether a text is an algorithm / listing caption,
 * e.g., "(a) PyTorch-style pseudo code for chunkwise DPLR." or "Listing 1: Pseudo code..."
 */
export function isCodeCaption(text: string): boolean {
  if (!text) return false;
  const trimmed = text.trim();
  if (trimmed.length > 150) return false;

  return (
    /^\s*\([a-z0-9]+\)\s*(?:[A-Za-z0-9_-]+\s+)?(?:pseudo\s*code|code|algorithm|implementation)/i.test(trimmed) ||
    /^\s*(?:Listing|Algorithm)\s+\d+[a-z]?\s*[:\.]/i.test(trimmed) ||
    /^\s*(?:Sampled\s+API\s+List|Prompt\s+Template)\b/i.test(trimmed)
  );
}

/**
 * Determines whether a text block represents source code, JSON, prompt templates, or pseudocode.
 */
export function isCodeBlock(text: string): boolean {
  if (!text || text.trim().length < 8) return false;
  if (isCodeCaption(text)) return false;

  const trimmed = text.trim();

  // 1. Direct match on code / JSON / prompt header
  for (const pat of CODE_START_PATTERNS) {
    if (pat.test(trimmed)) return true;
  }

  // Check JSON key-value pair density
  const jsonPairMatches = trimmed.match(/"[a-zA-Z0-9_.-]+"\s*:\s*(?:"[^"]*"|\d+|true|false|null|\[|\{)/g);
  if (jsonPairMatches && jsonPairMatches.length >= 2) return true;

  // 2. Count code syntax indicators
  let score = 0;

  for (const pat of CODE_KEYWORD_PATTERNS) {
    if (pat.test(trimmed)) score += 2;
  }

  // Check for line indentation with colons, assignments, or JSON commas
  const lines = trimmed.split('\n');
  let codeLines = 0;
  for (const line of lines) {
    const l = line.trim();
    if (
      l.endsWith(':') ||
      l.endsWith(';') ||
      l.endsWith(',') ||
      l.includes(' = ') ||
      l.includes(' += ') ||
      l.includes(' @ ') ||
      l.includes(' <- ') ||
      l.includes(':=') ||
      /^\s*"[a-zA-Z0-9_]+"\s*:/.test(l)
    ) {
      codeLines++;
    }
  }

  if (lines.length > 2 && codeLines / lines.length >= 0.4) {
    score += 3;
  }

  // Check for special programming symbols frequency: '=', '(', ')', '[', ']', '->', '@', '{', '}'
  const codeSymbolMatches = trimmed.match(/([=()\[\]{}@+\-*\/<>:]+)/g);
  const symbolCount = codeSymbolMatches ? codeSymbolMatches.join('').length : 0;
  const ratio = symbolCount / trimmed.length;

  if (ratio > 0.12 && lines.length >= 2) {
    score += 2;
  }

  return score >= 3;
}

/**
 * Checks whether a code block begins a new function, class, or algorithm definition.
 */
export function isCodeStart(text: string): boolean {
  if (!text) return false;
  return /^\s*(?:def\s+[a-zA-Z0-9_]|class\s+[a-zA-Z0-9_]|Algorithm\s+\d|Listing\s+\d|Procedure\s+[a-zA-Z0-9_]|function\s+[a-zA-Z0-9_]|system_prompt\s*:|user_prompt\s*:|diversity_user_prompt\s*:|Finish_function_description\s*:|\{\s*"|\[\s*\{)/im.test(text.trim());
}

/**
 * Checks whether a line looks like an academic section heading (e.g. "6.3 Complexity Analysis")
 */
export function isSectionHeading(text: string): boolean {
  if (!text) return false;
  return /^(?:\d+\.?\d*|[I|V|X]+\.?)\s+[A-Z]/.test(text.trim());
}

/**
 * Matches an associated caption to a specific code snippet based on keywords or tags ((a), (b), etc.)
 */
export function matchCodeCaption<T extends { en?: string; zh?: string }>(
  snippetText: string,
  captions: T[],
  snippetIdx: number
): T | undefined {
  if (!captions || captions.length === 0) return undefined;
  if (captions.length === 1) return captions[0];

  const sLower = snippetText.toLowerCase();

  // Match by keyword in caption
  for (const cap of captions) {
    const words = (cap.en || '')
      .toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .split(/\s+/)
      .filter(w => w.length >= 3 && !['pseudo', 'code', 'pytorch', 'style', 'for', 'snippet'].includes(w));
    for (const w of words) {
      if (sLower.includes(w)) return cap;
    }
  }

  // Match by (a), (b), (c)...
  const tag = String.fromCharCode(97 + snippetIdx);
  for (const cap of captions) {
    if ((cap.en || '').toLowerCase().includes(`(${tag})`)) return cap;
  }

  return captions[snippetIdx] || captions[0];
}

/**
 * Cleans code text from common OCR artifacts (e.g. broken symbols, weird spaces in dots).
 */
export function cleanCodeText(code: string): string {
  if (!code) return '';
  return code
    .replace(/\r\n/g, '\n')
    .replace(/\n\s*→\s*/g, ' ')
    .replace(/→/g, '->')
    .replace(/\\dots\b/g, '...')
    .replace(/\b([a-zA-Z0-9_]+)\s*\.\s+([a-zA-Z0-9_]+)\b/g, '$1.$2')
    .replace(/\.\s+([a-zA-Z0-9_]+)/g, '.$1');
}

/**
 * Identifies the programming language or pseudocode dialect.
 */
export function detectCodeLanguage(code: string): string {
  if (/^\s*(?:\{|\[|\},\s*\{)/.test(code) || /"(?:tool_description|api_list|properties|parameters|name)"\s*:/i.test(code)) return 'JSON';
  if (/\b(?:system_prompt|user_prompt|diversity_user_prompt|task_description|Finish_function_description)\b/i.test(code)) return 'Prompt';
  if (/\b(?:torch|nn|rearrange|tensor)\b/i.test(code)) return 'PyTorch';
  if (/\b(?:def|import|from|self|class|elif)\b/.test(code)) return 'Python';
  if (/\b(?:Algorithm|Input|Output|Step|Require|Ensure|while\s+.+?\bdo\b|for\s+each\b)\b/i.test(code)) return 'Pseudocode';
  if (/\b(?:cuda|__global__|__device__)\b/.test(code)) return 'CUDA / C++';
  return 'Code';
}


