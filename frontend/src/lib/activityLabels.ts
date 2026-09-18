/**
 * Human labels for tool/skill ids shown in chat.
 * Keep wire names (`web_search`, …) for the agent; only the UI uses these.
 */

const TOOL_KEYS: Record<string, string> = {
  web_search: 'chat.toolWebSearch',
  fetch_url: 'chat.toolFetchUrl',
  read_uploaded_file: 'chat.toolReadFile',
  search_uploaded_files: 'chat.toolSearchFiles',
  list_uploaded_files: 'chat.toolListFiles',
  write_file: 'chat.toolWriteFile',
  run_python: 'chat.toolRunPython',
  view_image: 'chat.toolViewImage',
  calculate: 'chat.toolCalculate',
  current_time: 'chat.toolCurrentTime',
  remember: 'chat.toolRemember',
  forget: 'chat.toolForget',
  list_memories: 'chat.toolListMemories',
  read_skill: 'chat.toolReadSkill',
}

const SKILL_KEYS: Record<string, string> = {
  'planning-with-intention': 'chat.skillPlanning',
  'working-with-documents': 'chat.skillDocuments',
  'file-reading': 'chat.skillFileReading',
  'replying-bilingually': 'chat.skillBilingual',
  'diagnosing-problems': 'chat.skillDiagnosing',
  'writing-deliverables': 'chat.skillDeliverables',
  'writing-guidelines': 'chat.skillWriting',
  research: 'chat.skillResearch',
  'answering-well': 'chat.skillAnswering',
  grilling: 'chat.skillGrilling',
  teach: 'chat.skillTeach',
  'to-questionnaire': 'chat.skillQuestionnaire',
  'writing-beats': 'chat.skillBeats',
  'writing-fragments': 'chat.skillFragments',
  'writing-shape': 'chat.skillShape',
}

/** `planning-with-intention` → `Planning with intention` */
export function humanizeKebab(id: string): string {
  return id
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

type Translate = (key: string, options?: Record<string, string | number>) => string

export function toolDisplayName(name: string, t: Translate): string {
  const key = TOOL_KEYS[name]
  if (key) {
    const label = t(key)
    if (label && label !== key) return label
  }
  return humanizeKebab(name)
}

export function skillDisplayName(name: string, t: Translate): string {
  const key = SKILL_KEYS[name]
  if (key) {
    const label = t(key)
    if (label && label !== key) return label
  }
  return humanizeKebab(name)
}
