export type BlockType =
  | 'scene_heading'
  | 'action'
  | 'character'
  | 'dialogue'
  | 'parenthetical'
  | 'transition'
  | 'shot'

export type ScreenplayBlock = {
  id: number
  type: BlockType
  text: string
  position: number
}

export type Scene = {
  id: number
  act_id: number
  number: number
  title: string
  description: string
  writer_notes: string
  completed: boolean
  timeline_position: number | null
  timeline_context: 'present' | 'flashback' | 'dream' | 'alternate' | 'unreliable' | 'unspecified'
  blocks: ScreenplayBlock[]
}

export type StoryEntityKind = 'characters' | 'relationships' | 'conflicts' | 'locations' | 'events'
export type StoryEntity = Record<string, unknown> & { id: number; project_id: number; evidence: string; confirmation_status: string; source_type: string }
export type StoryEntityRevision = { id: number; entity_type: string; entity_id: number | null; action: 'created' | 'updated' | 'deleted' | 'merged'; snapshot: Record<string, unknown>; changed_at: string }
export type ContinuityFinding = {
  id: number
  finding_type: string
  description: string
  severity: 'info' | 'warning' | 'important'
  confidence: number
  relevant_character_ids: number[]
  relevant_scene_ids: number[]
  evidence_refs: Record<string, unknown>[]
  disposition: 'unreviewed' | 'accepted_intentional' | 'needs_correction' | 'explained' | 'dismissed'
  writer_explanation: string
  resolution_status: 'open' | 'resolved'
  detected_at: string
}

export type Act = {
  id: number
  number: number
  title: string
  scenes: Scene[]
}

export type Project = {
  id: number
  title: string
  format: string
  genre: string
  runtime: string
  language: string
  premise: string
  setup_step: 'questions' | 'review' | 'complete'
  updated_at: string
  acts: Act[]
}

export type StorySetupAnswer = {
  status: 'answered' | 'skipped' | 'undecided'
  response: string
}

export type StorySetupState = {
  step: 'questions' | 'review' | 'complete'
  answers: Record<string, StorySetupAnswer>
}

export type TutorialState = {
  welcome_dismissed: boolean
  completed: Record<string, boolean>
}

export type StoryFact = {
  id: number
  category: string
  label: string
  value: string
  status: 'confirmed' | 'provisional' | 'inferred' | 'undecided'
  source: string
  original_value: string | null
  evidence: string
  source_text: string | null
  writer_confirmed: boolean
  intentionally_undecided: boolean
  modified_at: string
}

export type StoryFactRevision = {
  id: number
  fact_id: number | null
  action: 'created' | 'updated' | 'deleted'
  category: string
  label: string
  original_value: string | null
  value: string
  status: StoryFact['status']
  source: string
  evidence: string
  source_text: string | null
  writer_confirmed: boolean
  intentionally_undecided: boolean
  changed_at: string
}

export type AIResponse = {
  response: string
  model: string
}

export type NarrativeStatus = 'EXPLICIT' | 'INFERRED' | 'UNDECIDED' | 'NOT_APPLICABLE'
export type PremiseElementKey =
  | 'protagonist'
  | 'antagonist'
  | 'central_conflict'
  | 'external_conflict'
  | 'internal_conflict'
  | 'character_motivations'
  | 'character_goals'
  | 'stakes'
  | 'genre'
  | 'setting'
  | 'theme'
  | 'central_dramatic_question'
  | 'important_relationships'
  | 'potential_structure'

export type NarrativeElement = {
  value: string | null
  status: NarrativeStatus
  evidence: string
  source: 'premise' | 'writer' | 'ai_inference'
  confidence: number
  explanation: string
  writer_confirmed: boolean
  intentionally_undecided: boolean
}

export type PremiseMention = {
  category: 'character' | 'character_name' | 'character_role' | 'character_description' | 'organization' | 'object' | 'event' | 'action' | 'time_reference' | 'relationship' | 'location' | 'motivation_or_goal'
  value: string
  status: 'EXPLICIT'
  evidence: string
  source: 'premise'
  source_start: number | null
  source_end: number | null
  extraction_method: 'regex'
  confirmation_status: 'unconfirmed' | 'writer_confirmed'
  confidence: number
  explanation: string
}

export type PremiseAnalysis = {
  premise: string
  narrative_elements: Record<PremiseElementKey, NarrativeElement>
  antagonist_classification:
    | 'explicit_antagonist'
    | 'potential_antagonist'
    | 'antagonistic_force'
    | 'undecided'
    | 'no_conventional_antagonist'
}

export const antagonistClassificationLabels: Record<PremiseAnalysis['antagonist_classification'], string> = {
  explicit_antagonist: 'Explicit antagonist',
  potential_antagonist: 'Potential antagonist (unconfirmed)',
  antagonistic_force: 'Antagonistic force',
  undecided: 'Antagonist role undecided',
  no_conventional_antagonist: 'No conventional antagonist',
}

export type WriterNarrativeStatus = NarrativeStatus

export type PremiseQuestion = {
  id: number
  element_key: PremiseElementKey
  question: string
  premise_snapshot: string
  status: 'pending' | 'answered' | 'skipped' | 'undecided' | 'not_applicable' | 'superseded'
  response: string
  created_at: string
  answered_at: string | null
}

export type PremiseDevelopment = {
  analysis: PremiseAnalysis | null
  conversation: PremiseQuestion[]
  current_question: PremiseQuestion | null
  extractions: PremiseMention[]
  gaps: Array<{ element_key: PremiseElementKey; importance: 'CRITICAL' | 'IMPORTANT' | 'OPTIONAL' }>
  foundation: FoundationElement[]
  analysis_mode: 'ai' | 'deterministic' | null
  analysis_notice: string | null
}

export type FoundationElement = {
  key: string
  label: string
  status: 'established' | 'partially_established' | 'undecided' | 'intentionally_deferred' | 'not_applicable'
  explanation: string
  next_consideration: string | null
}

export const premiseElementLabels: Record<PremiseElementKey, string> = {
  protagonist: 'Protagonist',
  antagonist: 'Antagonist / force',
  central_conflict: 'Central conflict',
  external_conflict: 'External conflict',
  internal_conflict: 'Internal conflict',
  character_motivations: 'Character motivations',
  character_goals: 'Character goals',
  stakes: 'Stakes',
  genre: 'Genre',
  setting: 'Setting',
  theme: 'Theme',
  central_dramatic_question: 'Dramatic question',
  important_relationships: 'Relationships',
  potential_structure: 'Potential structure',
}
