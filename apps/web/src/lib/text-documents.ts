import type { DocumentIn } from "@qdrant-multitenant-rag-tiering/shared";

export const ACCEPTED_EXTENSIONS = [".txt", ".md"] as const;
export const MAX_DOCUMENT_BYTES = 200_000;
export const MAX_DOCUMENTS = 20;

/** Only the reading is async; validation is pure so it is unit-tested. */
export function documentProblems(files: { name: string; size: number }[]): string[] {
  const problems: string[] = [];
  if (files.length > MAX_DOCUMENTS) {
    problems.push(`Pick at most ${MAX_DOCUMENTS} files.`);
  }
  const seen = new Set<string>();
  for (const file of files) {
    const lower = file.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      problems.push(`${file.name}: only .txt and .md files are indexed.`);
    }
    if (file.size > MAX_DOCUMENT_BYTES) {
      problems.push(`${file.name}: larger than ${MAX_DOCUMENT_BYTES / 1000} KB.`);
    }
    if (file.size === 0) {
      problems.push(`${file.name}: the file is empty.`);
    }
    if (seen.has(file.name)) {
      problems.push(`${file.name}: picked twice.`);
    }
    seen.add(file.name);
  }
  return problems;
}

export async function readDocuments(files: File[]): Promise<DocumentIn[]> {
  return Promise.all(
    files.map(async (file) => ({ filename: file.name, text: await file.text() }))
  );
}
