import type {
  AIResponse, BlockType, PremiseDevelopment, Project, ScreenplayBlock, StoryFact,
  StoryFactRevision, WriterNarrativeStatus, PremiseElementKey,
  StorySetupState, TutorialState,
  StoryEntity, StoryEntityKind, StoryEntityRevision, ContinuityFinding,
} from './types'

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  listProjects: () => request<Project[]>('/projects'),
  createProject: (values: Partial<Project> & { setup_flow?: boolean }) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(values) }),
  getStorySetup: (projectId: number) =>
    request<StorySetupState>(`/projects/${projectId}/setup`),
  updateStorySetup: (projectId: number, values: StorySetupState) =>
    request<StorySetupState>(`/projects/${projectId}/setup`, {
      method: 'PUT',
      body: JSON.stringify(values),
    }),
  getTutorialState: () => request<TutorialState>('/preferences/tutorials'),
  updateTutorialState: (values: TutorialState) =>
    request<TutorialState>('/preferences/tutorials', { method: 'PUT', body: JSON.stringify(values) }),
  updateProject: (id: number, values: Partial<Project>) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(values) }),
  createAct: (projectId: number) =>
    request<Project>(`/projects/${projectId}/acts`, { method: 'POST', body: '{}' }),
  createScene: (projectId: number, actId: number) =>
    request<Project>(`/projects/${projectId}/acts/${actId}/scenes`, { method: 'POST', body: '{}' }),
  updateScene: (
    projectId: number,
    sceneId: number,
    values: Partial<Pick<ScenePayload, 'title' | 'description' | 'writer_notes' | 'completed' | 'blocks' | 'timeline_position' | 'timeline_context'>>,
  ) => request<Project>(`/projects/${projectId}/scenes/${sceneId}`, {
    method: 'PUT',
    body: JSON.stringify(values),
  }),
  deleteScene: (projectId: number, sceneId: number) =>
    request<Project>(`/projects/${projectId}/scenes/${sceneId}`, { method: 'DELETE' }),
  reorderScene: (projectId: number, sceneId: number, direction: 'up' | 'down') =>
    request<Project>(`/projects/${projectId}/scenes/${sceneId}/reorder`, {
      method: 'POST',
      body: JSON.stringify({ direction }),
    }),
  moveScene: (projectId: number, sceneId: number, target: { actId: number; sceneId?: number }) =>
    request<Project>(`/projects/${projectId}/scenes/${sceneId}/reorder`, {
      method: 'POST',
      body: JSON.stringify(target.sceneId
        ? { target_scene_id: target.sceneId }
        : { target_act_id: target.actId }),
    }),
  listFacts: (projectId: number) => request<StoryFact[]>(`/projects/${projectId}/facts`),
  listFactHistory: (projectId: number) =>
    request<StoryFactRevision[]>(`/projects/${projectId}/facts/history`),
  createFact: (
    projectId: number,
    values: Pick<StoryFact, 'category' | 'label' | 'value' | 'status' | 'source'>
      & Partial<Pick<StoryFact, 'evidence' | 'source_text' | 'writer_confirmed' | 'intentionally_undecided'>>,
  ) =>
    request<StoryFact>(`/projects/${projectId}/facts`, { method: 'POST', body: JSON.stringify(values) }),
  updateFact: (
    projectId: number,
    factId: number,
    values: Omit<StoryFact, 'id' | 'original_value' | 'modified_at'>,
  ) => request<StoryFact>(`/projects/${projectId}/facts/${factId}`, {
    method: 'PUT',
    body: JSON.stringify(values),
  }),
  deleteFact: (projectId: number, factId: number) =>
    request<void>(`/projects/${projectId}/facts/${factId}`, { method: 'DELETE' }),
  listStoryEntities: (projectId: number, kind: StoryEntityKind) => request<StoryEntity[]>(`/projects/${projectId}/story-bible/entities/${kind}`),
  createStoryEntity: (projectId: number, kind: StoryEntityKind, values: Record<string, unknown>) => request<StoryEntity>(`/projects/${projectId}/story-bible/entities/${kind}`, { method: 'POST', body: JSON.stringify(values) }),
  updateStoryEntity: (projectId: number, kind: StoryEntityKind, id: number, values: Record<string, unknown>) => request<StoryEntity>(`/projects/${projectId}/story-bible/entities/${kind}/${id}`, { method: 'PUT', body: JSON.stringify(values) }),
  deleteStoryEntity: (projectId: number, kind: StoryEntityKind, id: number) => request<void>(`/projects/${projectId}/story-bible/entities/${kind}/${id}`, { method: 'DELETE' }),
  listStoryEntityHistory: (projectId: number) => request<StoryEntityRevision[]>(`/projects/${projectId}/story-bible/history`),
  analyzeContinuity: (projectId: number) => request<{ findings: ContinuityFinding[]; analyzed_scenes: number; message: string }>(`/projects/${projectId}/continuity/analyze`, { method: 'POST', body: '{}' }),
  listContinuityFindings: (projectId: number) => request<ContinuityFinding[]>(`/projects/${projectId}/continuity/findings`),
  updateContinuityFinding: (projectId: number, id: number, disposition: ContinuityFinding['disposition'], writer_explanation = '') => request<ContinuityFinding>(`/projects/${projectId}/continuity/findings/${id}`, { method: 'PUT', body: JSON.stringify({ disposition, writer_explanation }) }),
  askAI: (projectId: number, sceneId: number | null, prompt: string) =>
    request<AIResponse>(`/projects/${projectId}/assistant`, {
      method: 'POST',
      body: JSON.stringify({ scene_id: sceneId, prompt }),
    }),
  askAIStream: async (
    projectId: number,
    sceneId: number | null,
    prompt: string,
    onChunk: (content: string) => void,
  ): Promise<AIResponse> => {
    const response = await fetch(`/api/projects/${projectId}/assistant/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene_id: sceneId, prompt }),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: string } | null
      throw new Error(body?.detail ?? `Request failed (${response.status})`)
    }
    if (!response.body) throw new Error('Ollama streaming is not available in this browser.')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let content = ''
    let model = 'Ollama'
    let completed = false
    const consume = (frame: string) => {
      const data = frame.split('\n').find((line) => line.startsWith('data: '))?.slice(6)
      if (!data) return
      let event: { type: string; content?: string; model?: string; message?: string }
      try {
        event = JSON.parse(data) as typeof event
      } catch {
        throw new Error('Ollama returned an invalid streaming response. Retry the request.')
      }
      if (event.type === 'token' && event.content) {
        content += event.content
        onChunk(event.content)
      } else if (event.type === 'done') {
        completed = true
        model = event.model ?? model
      } else if (event.type === 'error') {
        throw new Error(event.message ?? 'Ollama could not complete the request.')
      }
    }

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
        let boundary = buffer.indexOf('\n\n')
        while (boundary >= 0) {
          consume(buffer.slice(0, boundary))
          buffer = buffer.slice(boundary + 2)
          boundary = buffer.indexOf('\n\n')
        }
      }
      buffer += decoder.decode()
      if (buffer.trim()) consume(buffer)
    } finally {
      reader.releaseLock()
    }
    if (!completed) throw new Error('The Ollama stream ended before the response was complete. Retry the request.')
    if (!content.trim()) throw new Error('Ollama returned an empty response. Check the model settings and retry.')
    return { response: content, model }
  },
  getDevelopment: (projectId: number) =>
    request<PremiseDevelopment>(`/projects/${projectId}/development`),
  analyzePremise: (projectId: number) =>
    request<PremiseDevelopment>(`/projects/${projectId}/development/analyze`, { method: 'POST' }),
  nextPremiseQuestion: (projectId: number) =>
    request<PremiseDevelopment>(`/projects/${projectId}/development/next-question`, { method: 'POST' }),
  answerPremiseQuestion: (
    projectId: number,
    questionId: number,
    status: 'answered' | 'skipped' | 'undecided' | 'not_applicable',
    response = '',
  ) => request<PremiseDevelopment>(
    `/projects/${projectId}/development/questions/${questionId}`,
    { method: 'POST', body: JSON.stringify({ status, response }) },
  ),
  reopenPremiseQuestion: (projectId: number, questionId: number) =>
    request<PremiseDevelopment>(
      `/projects/${projectId}/development/questions/${questionId}/reopen`,
      { method: 'POST' },
    ),
  updatePremiseElement: (
    projectId: number,
    elementKey: PremiseElementKey,
    status: WriterNarrativeStatus,
    value: string | null,
  ) => request<PremiseDevelopment>(
    `/projects/${projectId}/development/elements/${elementKey}`,
    { method: 'PUT', body: JSON.stringify({ status, value }) },
  ),
}

type ScenePayload = {
  title: string
  description: string
  writer_notes: string
  completed: boolean
  timeline_position: number | null
  timeline_context: 'present' | 'flashback' | 'dream' | 'alternate' | 'unreliable' | 'unspecified'
  blocks: Array<Pick<ScreenplayBlock, 'type' | 'text'> & { id?: number }>
}

export const blockTypes: Array<{ value: BlockType; label: string }> = [
  { value: 'scene_heading', label: 'Scene heading' },
  { value: 'action', label: 'Action' },
  { value: 'character', label: 'Character' },
  { value: 'dialogue', label: 'Dialogue' },
  { value: 'parenthetical', label: 'Parenthetical' },
  { value: 'transition', label: 'Transition' },
  { value: 'shot', label: 'Shot' },
]

export const blockLabel = (type: BlockType) =>
  blockTypes.find((item) => item.value === type)?.label ?? 'Action'
