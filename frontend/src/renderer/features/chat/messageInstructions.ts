export function missingInputInstruction(skillName: string | null | undefined, missingInputs: Array<Record<string, unknown>>) {
  const normalizedSkill = String(skillName ?? "").trim();
  const names = new Set(missingInputs.map((item) => String(item.name ?? "").trim()));
  const labels = new Set(missingInputs.map((item) => String(item.label ?? "").trim()));
  if (normalizedSkill === "audio-transcription" || names.has("audio_source") || labels.has("音频或视频文件")) {
    return "请先在当前会话上传或从项目文件中引用一个音频/视频文件，然后重新发送“将这段录音转录成文字”。支持 MP3、WAV、M4A、OGG、FLAC、MP4、MOV 等格式。";
  }
  if (normalizedSkill === "term-correction" || normalizedSkill === "术语纠错" || names.has("term_corrections")) {
    return "请提供术语纠正规则，每行一条，例如：LAM Wiki -> LLM Wiki。";
  }
  const fields = missingInputs
    .map((item) => String(item.label ?? item.name ?? "待补充字段").trim())
    .filter(Boolean)
    .join("、");
  return fields ? `请补充：${fields}。` : "";
}
