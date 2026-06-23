const CODE_LANGUAGES = new Set([
  "python", "py", "javascript", "js", "typescript", "ts", "tsx", "jsx",
  "bash", "sh", "shell", "zsh", "json", "yaml", "yml", "sql", "html", "css",
  "java", "go", "rust", "c", "cpp", "csharp", "cs", "ruby", "rb", "php",
  "swift", "kotlin", "powershell", "ps1", "dockerfile", "xml", "toml", "ini",
]);

const DOCUMENT_LANGUAGES = new Set([
  "text", "markdown", "md", "email", "plain", "plaintext", "txt", "mail",
]);

export function shouldRenderAsDocumentBlock(language: string | undefined, code: string): boolean {
  const lang = (language || "").trim().toLowerCase();
  if (DOCUMENT_LANGUAGES.has(lang)) return true;
  if (lang && CODE_LANGUAGES.has(lang)) return false;
  if (lang) return false;
  if (/^\s*(def |function |import |class |const |let |var |#include|public static|SELECT |CREATE |<!DOCTYPE)/im.test(code)) {
    return false;
  }
  const lines = code.split("\n");
  if (lines.length === 1 && code.length <= 120 && !/[{;<>$\\]/.test(code)) return true;
  if (lines.length >= 2 && !lines.some((line) => /^\s*(import|from|def|class|function|const|let|var)\s/.test(line))) {
    return true;
  }
  return false;
}
