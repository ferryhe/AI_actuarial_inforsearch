export interface ChatKnowledgeBaseReference {
  kb_id: string;
  usable?: boolean;
}

export interface CategorizedKnowledgeBaseReference {
  id?: string;
  kb_id?: string;
  categories?: string[];
}

function knowledgeBaseId(kb: CategorizedKnowledgeBaseReference): string {
  return String(kb.kb_id || kb.id || "").trim();
}

function normalizedCategoryKeys(categories: unknown): string[] {
  if (!Array.isArray(categories)) return [];
  return Array.from(new Set(
    categories
      .filter((category): category is string => typeof category === "string")
      .map((category) => category.trim())
      .filter(Boolean),
  ));
}

export function isChatKnowledgeBaseAvailable(
  kb: ChatKnowledgeBaseReference | undefined,
): boolean {
  return Boolean(kb?.kb_id) && kb?.usable !== false;
}

export function getAvailableChatKnowledgeBaseIds(
  knowledgeBases: readonly ChatKnowledgeBaseReference[],
): Set<string> {
  return new Set(
    knowledgeBases
      .filter(isChatKnowledgeBaseAvailable)
      .map((kb) => kb.kb_id),
  );
}

export function findDedicatedCategoryKnowledgeBaseId(
  categoryKey: string,
  categorizedKnowledgeBases: readonly CategorizedKnowledgeBaseReference[],
  chatKnowledgeBases: readonly ChatKnowledgeBaseReference[],
): string | null {
  const normalizedCategoryKey = categoryKey.trim();
  if (!normalizedCategoryKey) return null;

  const dedicatedIds = new Set<string>();
  for (const kb of categorizedKnowledgeBases) {
    const categories = normalizedCategoryKeys(kb.categories);
    const kbId = knowledgeBaseId(kb);
    if (kbId && categories.length === 1 && categories[0] === normalizedCategoryKey) {
      dedicatedIds.add(kbId);
    }
  }
  if (dedicatedIds.size !== 1) return null;

  const [dedicatedKbId] = dedicatedIds;
  return getAvailableChatKnowledgeBaseIds(chatKnowledgeBases).has(dedicatedKbId)
    ? dedicatedKbId
    : null;
}
