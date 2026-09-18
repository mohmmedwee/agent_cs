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
  ask_user: 'chat.toolAskUser',
  write_file: 'chat.toolWriteFile',
  convert_upload_to_docx: 'chat.toolConvertUpload',
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

function parseArgsObject(args: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(args) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    /* partial JSON while streaming */
  }
  return null
}

function stringField(raw: string, key: string): string {
  const parsed = parseArgsObject(raw)
  const value = parsed?.[key]
  if (typeof value === 'string' && value.trim()) return value.trim()
  const match = new RegExp(`"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`).exec(raw)
  if (!match) return ''
  try {
    return JSON.parse(`"${match[1]}"`) as string
  } catch {
    return match[1].replace(/\\n/g, '\n').replace(/\\"/g, '"')
  }
}

/** Extract `code` from run_python args, including partial JSON while streaming. */
export function pythonCodeFromArgs(args: string): string {
  const parsed = parseArgsObject(args)
  if (typeof parsed?.code === 'string') return parsed.code
  const match = /"code"\s*:\s*"((?:\\.|[^"\\])*)"/.exec(args)
  if (!match) return ''
  try {
    return JSON.parse(`"${match[1]}"`) as string
  } catch {
    return match[1].replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\')
  }
}

/**
 * Friendly one-line tool detail for the activity trail — never raw JSON.
 * Returns null when there is nothing useful to show.
 */
export function toolDetail(name: string, args: string, t: Translate): string | null {
  const trimmed = args.trim()
  const parsed = parseArgsObject(trimmed)
  if (parsed && Object.keys(parsed).length === 0) return null
  if (!trimmed || trimmed === '{}') return null

  if (name === 'run_python') {
    const code = pythonCodeFromArgs(args)
    if (!code.trim()) return null
    const lines = code.split('\n')
    const first =
      lines.find((line) => {
        const value = line.trim()
        return value.length > 0 && !value.startsWith('#')
      })?.trim() ?? ''
    const count = lines.length
    const lineLabel = t('chat.lineCount', { count })
    if (!first) return lineLabel
    const clipped = first.length > 72 ? `${first.slice(0, 72)}…` : first
    return `${clipped} · ${lineLabel}`
  }

  if (
    name === 'list_uploaded_files' ||
    name === 'list_files' ||
    name === 'list_memories' ||
    name === 'current_time'
  ) {
    return null
  }

  if (
    name === 'write_file' ||
    name === 'read_uploaded_file' ||
    name === 'read_file' ||
    name === 'convert_upload_to_docx' ||
    name === 'view_image'
  ) {
    const fileName =
      stringField(args, 'name') ||
      stringField(args, 'source') ||
      stringField(args, 'path') ||
      stringField(args, 'file')
    return fileName || null
  }

  if (name === 'web_search') {
    const query = stringField(args, 'query')
    return query ? `“${query}”` : null
  }

  if (name === 'fetch_url') {
    const url = stringField(args, 'url')
    if (!url) return null
    try {
      return new URL(url).hostname
    } catch {
      return url
    }
  }

  if (name === 'calculate') {
    const expression = stringField(args, 'expression')
    return expression || null
  }

  if (name === 'search_uploaded_files') {
    const query = stringField(args, 'query')
    return query ? `“${query}”` : null
  }

  if (parsed) {
    for (const value of Object.values(parsed)) {
      if (typeof value === 'string' && value.trim()) {
        const clipped = value.trim()
        return clipped.length > 72 ? `${clipped.slice(0, 72)}…` : clipped
      }
    }
    return null
  }

  // Last resort while args are still streaming — never dump raw JSON.
  return null
}
