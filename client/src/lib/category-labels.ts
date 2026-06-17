export interface CategoryLabelOption {
  name: string;
  label?: string;
  labels?: { en?: string; zh?: string };
  count?: number | null;
}

const CATEGORY_LABELS_ZH: Record<string, string> = {
  "AI": "人工智能",
  "Climate & ESG": "气候与 ESG",
  "Data & Analytics": "数据与分析",
  "Education / Events": "教育与活动",
  "Exam": "考试",
  "Fintech & InsurTech": "金融科技与保险科技",
  "Health": "健康险",
  "Investment / ALM": "投资与资产负债管理",
  "Life": "寿险",
  "LTC / DI / CI": "长期护理 / 失能 / 重疾",
  "Operations / Automation": "运营与自动化",
  "Other": "其他",
  "P&C": "财产与意外险",
  "Pension & Retirement": "养老金与退休",
  "Pricing": "定价",
  "Regulation & Standards": "监管与准则",
  "Reserving": "准备金",
  "Risk & Capital": "风险与资本",
  "Underwriting & Claims": "核保与理赔",
};

export function categoryValue(category: string | CategoryLabelOption | null | undefined): string {
  if (!category) return "";
  return typeof category === "string" ? category : category.name;
}

export function categoryDisplayName(
  category: string | CategoryLabelOption | null | undefined,
  lang: string,
): string {
  const name = categoryValue(category).trim();
  if (!name) return "-";
  if (typeof category !== "string") {
    const localized = category.labels?.[lang as "en" | "zh"] || category.label;
    if (localized && localized.trim()) return localized.trim();
  }
  if (lang === "zh") return CATEGORY_LABELS_ZH[name] || name;
  return name;
}
