import { describe, expect, it } from "vitest";

import { documentProblems, MAX_DOCUMENT_BYTES, readDocuments } from "./text-documents";

describe("documentProblems", () => {
  it("accepts text and markdown files", () => {
    expect(documentProblems([{ name: "a.md", size: 10 }, { name: "B.TXT", size: 5 }])).toEqual([]);
  });

  it("rejects other formats, empty, oversized and duplicate files", () => {
    const problems = documentProblems([
      { name: "scan.pdf", size: 10 },
      { name: "empty.txt", size: 0 },
      { name: "big.md", size: MAX_DOCUMENT_BYTES + 1 },
      { name: "a.md", size: 1 },
      { name: "a.md", size: 1 },
    ]);
    expect(problems).toHaveLength(4);
    expect(problems.join(" ")).toMatch(/scan\.pdf.*empty\.txt.*big\.md.*a\.md: picked twice/);
  });
});

describe("readDocuments", () => {
  it("reads file text into the API's document shape", async () => {
    const docs = await readDocuments([new File(["# Hi"], "notes.md", { type: "text/markdown" })]);
    expect(docs).toEqual([{ filename: "notes.md", text: "# Hi" }]);
  });
});
