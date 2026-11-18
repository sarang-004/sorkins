import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDown, ArrowRight, ArrowUp, BookOpen, Check, ChevronDown, ChevronRight,
  CircleHelp, Clapperboard, Download, FilePlus2, Film, Lightbulb, LoaderCircle, Menu,
  MessageSquareText, Plus, Printer, Save, Send, Settings2,
  RotateCcw, ShieldCheck, Sparkles, Trash2, X,
} from 'lucide-react'
import { api, blockLabel, blockTypes } from './api'
import { StoryBibleStructured } from './StoryBibleStructured'
import {
  antagonistClassificationLabels,
  premiseElementLabels,
  type Act,
  type AIResponse,
  type BlockType,
  type PremiseDevelopment,
  type PremiseElementKey,
  type NarrativeStatus,
  type Project,
  type Scene,
  type ScreenplayBlock,
  type StoryFact,
  type StoryFactRevision,
  type StorySetupAnswer,
  type StorySetupState,
  type TutorialState,
} from './types'
import './App.css'

type Panel = 'assistant' | 'bible'
type SaveState = 'saved' | 'saving' | 'error'
type LoadedDevelopment = PremiseDevelopment & { projectId: number }
type ProjectDetails = Pick<Project, 'title' | 'format' | 'genre' | 'runtime' | 'language' | 'premise'>
type SetupQuestion = {
  id: string
  section: string
  title: string
  explanation: string
  label: string
  options?: string[]
}

const setupQuestions: SetupQuestion[] = [
  { id: 'protagonist', section: 'Protagonist', title: 'Who is the main character of your story?', explanation: 'A name, a role, or a rough description is a good starting point.', label: 'Main character' },
  { id: 'goal', section: 'Protagonist', title: 'What do they want or hope to achieve?', explanation: 'This can be a concrete goal or something they are longing for.', label: 'Protagonist goal' },
  { id: 'motivation', section: 'Protagonist', title: 'Why is this important to them?', explanation: 'Share what you know; it is fine if their deeper reasons are still emerging.', label: 'Protagonist motivation' },
  { id: 'obstacles', section: 'Protagonist', title: 'What is preventing them from achieving it?', explanation: 'Consider anything making the goal harder, including circumstances or their own choices.', label: 'Protagonist obstacles' },
  { id: 'stakes', section: 'Protagonist', title: 'What are they afraid of losing?', explanation: 'This helps clarify what matters if things do not go their way.', label: 'Stakes' },
  { id: 'opposition', section: 'Opposition', title: 'Who or what opposes the protagonist?', explanation: 'There does not need to be a conventional villain. It could be a person, a force, a situation, or an inner struggle.', label: 'Opposing force' },
  { id: 'opposition-goal', section: 'Opposition', title: 'What does this opposing force want?', explanation: 'Only answer if you have an idea; the opposition may not have a clear goal yet.', label: 'Opposing force goal' },
  { id: 'conflicting-goals', section: 'Opposition', title: 'Why are their goals in conflict?', explanation: 'Describe the clash as you currently understand it.', label: 'Opposing goals' },
  { id: 'opposition-kind', section: 'Opposition', title: 'What kind of opposition is it?', explanation: 'Choose the closest fit, or leave this open for now.', label: 'Opposition type', options: ['A person', 'An organisation', 'Society', 'Nature', 'Circumstances', 'An internal struggle', 'A combination', 'Something else'] },
  { id: 'central-conflict', section: 'Central Conflict', title: 'What is the main problem driving the story?', explanation: 'What situation keeps the protagonist moving, deciding, or struggling?', label: 'Central conflict' },
  { id: 'failure', section: 'Central Conflict', title: 'What happens if the protagonist fails?', explanation: 'The consequences can be personal, practical, or still uncertain.', label: 'Consequences of failure' },
  { id: 'difficulty', section: 'Central Conflict', title: 'What makes resolving this conflict difficult?', explanation: 'Think about the barriers, competing needs, or complications you already know.', label: 'Conflict obstacles' },
  { id: 'conflict-kind', section: 'Central Conflict', title: 'Where does the conflict mainly come from?', explanation: 'Pick a broad direction if useful. Stories can combine several kinds of conflict.', label: 'Conflict type', options: ['Within the protagonist', 'Between people', 'From outside circumstances', 'From society', 'A combination', 'Not sure yet'] },
  { id: 'supporting-characters', section: 'Supporting Characters', title: 'Who are the important people around the protagonist?', explanation: 'You can leave this open if you have not created supporting characters yet.', label: 'Supporting characters' },
  { id: 'supporting-roles', section: 'Supporting Characters', title: 'What role do they play in the story?', explanation: 'Their roles can be broad or still undecided.', label: 'Supporting character roles' },
  { id: 'relationships', section: 'Supporting Characters', title: 'How are they connected to the protagonist?', explanation: 'Describe only the relationships you have established so far.', label: 'Important relationships' },
  { id: 'location', section: 'Setting and World', title: 'Where does the story take place?', explanation: 'A specific place, a type of place, or a world you are still imagining all work.', label: 'Location' },
  { id: 'time', section: 'Setting and World', title: 'When does it take place?', explanation: 'Share a time period, season, or simply that you have not decided.', label: 'Time period' },
  { id: 'world-details', section: 'Setting and World', title: 'What is distinctive about this world?', explanation: 'Include any important rules, circumstances, or details that shape the story.', label: 'World details' },
  { id: 'dramatic-question', section: 'Story Direction', title: 'What central question does your story explore?', explanation: 'This might be a question the audience carries through the story; it is optional.', label: 'Central dramatic question' },
  { id: 'journey', section: 'Story Direction', title: 'What kind of journey does the protagonist go through?', explanation: 'Describe a change, challenge, or journey in broad terms if you have one.', label: 'Character journey' },
  { id: 'ending', section: 'Story Direction', title: 'Do you have an idea of how the story ends?', explanation: 'The ending is completely optional. You can decide it later.', label: 'Ending' },
]

const foundationFields = [
  ['protagonist', 'Protagonist'],
  ['goal', 'Protagonist goal'],
  ['central-conflict', 'Central conflict'],
  ['opposition', 'Opposing force'],
  ['stakes', 'Stakes'],
  ['location', 'Setting'],
] as const
const firstOpenSetupQuestion = (answers: StorySetupState['answers']) => {
  const index = setupQuestions.findIndex((question) => !answers[question.id])
  return index < 0 ? setupQuestions.length - 1 : index
}

type TutorialStep = { target: string; title: string; description: string }
const tutorialSteps: Record<string, TutorialStep[]> = {
  walkthrough: [
    { target: '[data-tour="project"]', title: 'Your project', description: 'Project details and settings live here. Create or switch between screenplays from the project menu.' },
    { target: '[data-tour="outline"]', title: 'Scenes and acts', description: 'Organise scenes by act, add scenes, and drag or reorder them in the outline. Edit a scene heading in the editor to rename it.' },
    { target: '[data-tour="editor"]', title: 'Screenplay editor', description: 'Write your screenplay here. Each scene is saved locally as you work.' },
    { target: '[data-tour="formatting"]', title: 'Screenplay elements', description: 'Use the element menu to add scene headings, action, character cues, dialogue, and other supported formats.' },
    { target: '[data-tour="story-bible"]', title: 'Story Bible', description: 'Review and edit established story facts. Inferences and undecided details are kept distinct from writer-confirmed facts.' },
    { target: '[data-tour="assistant"]', title: 'Writing assistant', description: 'Ask for analysis of your story or scene. It uses available project context, and suggestions never change your screenplay automatically.' },
    { target: '[data-tour="notes"]', title: 'Scene notes', description: 'Keep scene descriptions and private writer notes alongside your screenplay.' },
  ],
  editor: [
    { target: '[data-tour="editor"]', title: 'Writing a scene', description: 'Choose a scene in the outline, then write or revise its screenplay elements here.' },
    { target: '[data-tour="formatting"]', title: 'Formatting controls', description: 'Add screenplay elements from this menu. Use Tab to move between text elements.' },
  ],
  bible: [
    { target: '[data-tour="story-bible"]', title: 'Open the Story Bible', description: 'Use this tab to review and edit details that inform your story.' },
    { target: '[data-tour="bible-content"]', title: 'Review story facts', description: 'Writer-confirmed facts, inferences, and undecided details have separate statuses and are never silently merged.' },
  ],
  assistant: [
    { target: '[data-tour="assistant"]', title: 'Ask the assistant', description: 'Ask about established story facts or the current scene. AI suggestions are advisory; you make every creative decision.' },
    { target: '[data-tour="assistant-input"]', title: 'Your prompt', description: 'Describe the analysis you want. The local model is optional; the rest of the writing room remains available without it.' },
  ],
  scenes: [
    { target: '[data-tour="outline"]', title: 'Manage scenes', description: 'Create scenes with the plus buttons, expand acts, and drag or reorder scenes in the outline. Edit the scene heading in the editor to rename it.' },
    { target: '[data-tour="notes"]', title: 'Organise a scene', description: 'Open Scene notes to add a description and private notes for the selected scene.' },
  ],
}

const emptyTutorialState = { welcome_dismissed: false, completed: {} }
const contextualTips: Record<string, { title: string; description: string; tutorial: string }> = {
  bible: {
    title: 'Your Story Bible',
    description: 'This is where confirmed facts, provisional ideas, and intentionally undecided details are kept separate.',
    tutorial: 'bible',
  },
  assistant: {
    title: 'The writing assistant',
    description: 'Ask about established story facts or the current scene. Suggestions are advisory and never change your script.',
    tutorial: 'assistant',
  },
  scenes: {
    title: 'Managing scenes',
    description: 'Add scenes from an act, reorder them in the outline, and keep scene-specific notes in the editor.',
    tutorial: 'scenes',
  },
}

const blankProjectDetails: ProjectDetails = {
  title: '',
  format: 'Feature Film',
  genre: '',
  runtime: '',
  language: 'English',
  premise: '',
}

const emptyBlock = (type: BlockType, position: number): ScreenplayBlock => ({
  id: -Date.now() - position,
  type,
  text: '',
  position,
})

const flattenScenes = (acts: Act[]) => acts.flatMap((act) => act.scenes)

const saveText = (filename: string, content: string, mime: string) => {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([content], { type: mime }))
  link.download = filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

function App() {
  const [project, setProject] = useState<Project | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [activeSceneId, setActiveSceneId] = useState<number | null>(null)
  const [facts, setFacts] = useState<StoryFact[]>([])
  const [factHistory, setFactHistory] = useState<StoryFactRevision[]>([])
  const [panel, setPanel] = useState<Panel>('assistant')
  const [assistantPrompt, setAssistantPrompt] = useState('')
  const [assistantReply, setAssistantReply] = useState<AIResponse | null>(null)
  const [assistantLoading, setAssistantLoading] = useState(false)
  const [assistantStage, setAssistantStage] = useState('')
  const [assistantError, setAssistantError] = useState('')
  const [development, setDevelopment] = useState<LoadedDevelopment | null>(null)
  const [developmentProjectId, setDevelopmentProjectId] = useState<number | null>(null)
  const [developmentLoading, setDevelopmentLoading] = useState(false)
  const [developmentStage, setDevelopmentStage] = useState('')
  const [developmentError, setDevelopmentError] = useState('')
  const [setupState, setSetupState] = useState<StorySetupState | null>(null)
  const [setupAnswer, setSetupAnswer] = useState('')
  const [setupIndex, setSetupIndex] = useState(0)
  const [setupSaving, setSetupSaving] = useState(false)
  const [tutorialState, setTutorialState] = useState<TutorialState>(emptyTutorialState)
  const [showWelcome, setShowWelcome] = useState(false)
  const [dontShowWelcome, setDontShowWelcome] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [contextualTip, setContextualTip] = useState<string | null>(null)
  const [activeTutorial, setActiveTutorial] = useState<string | null>(null)
  const [tutorialIndex, setTutorialIndex] = useState(0)
  const [tourRect, setTourRect] = useState<{ top: number; left: number; width: number; height: number } | null>(null)
  const [premiseAnswer, setPremiseAnswer] = useState('')
  const [answerSaving, setAnswerSaving] = useState(false)
  const [error, setError] = useState('')
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showProjectForm, setShowProjectForm] = useState(false)
  const [showProjectSwitcher, setShowProjectSwitcher] = useState(false)
  const [editingProject, setEditingProject] = useState(false)
  const [projectForm, setProjectForm] = useState<ProjectDetails>(blankProjectDetails)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [showRightPanel, setShowRightPanel] = useState(false)
  const [openActs, setOpenActs] = useState<number[]>([])
  const [showNotes, setShowNotes] = useState(false)
  const [showFactForm, setShowFactForm] = useState(false)
  const [factForm, setFactForm] = useState({ label: '', value: '', category: 'Story fact' })
  const [statusMessage, setStatusMessage] = useState('')
  const saveTimer = useRef<number | undefined>(undefined)
  const developmentStageTimer = useRef<number | undefined>(undefined)
  const assistantStageTimer = useRef<number | undefined>(undefined)
  const failedAssistantPrompt = useRef('')
  const developmentRequests = useRef(new Map<number, string>())
  const activeProjectId = useRef<number | null>(null)

  const allScenes = useMemo(() => project ? flattenScenes(project.acts) : [], [project])
  const activeScene = allScenes.find((scene) => scene.id === activeSceneId) ?? allScenes[0] ?? null
  const currentDevelopment = development?.projectId === project?.id ? development : null
  const words = useMemo(() => (activeScene?.blocks ?? []).reduce(
    (total, block) => total + (block.type === 'dialogue' || block.type === 'action'
      ? block.text.trim().split(/\s+/).filter(Boolean).length
      : 0),
    0,
  ), [activeScene])
  const pageCount = Math.max(1, Math.ceil(allScenes.reduce(
    (total, scene) => total + scene.blocks.reduce((lines, block) => lines + Math.max(1, Math.ceil(block.text.length / 64)), 0),
    0,
  ) / 55))

  const refreshFacts = useCallback(async (projectId: number) => {
    try {
      const [nextFacts, nextHistory] = await Promise.all([
        api.listFacts(projectId),
        api.listFactHistory(projectId),
      ])
      setFacts(nextFacts)
      setFactHistory(nextHistory)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load the Story Bible.')
    }
  }, [])

  const runPremiseDevelopment = useCallback(async (target: Project) => {
    if (!target.premise.trim()) {
      setDevelopment(null)
      setDevelopmentProjectId(target.id)
      setDevelopmentError('')
      setDevelopmentLoading(false)
      setDevelopmentStage('')
      return
    }
    if (developmentRequests.current.get(target.id) === target.premise) return
    developmentRequests.current.set(target.id, target.premise)
    setDevelopmentProjectId(target.id)
    setDevelopment((current) => current?.projectId === target.id
      && current.analysis?.premise === target.premise
      ? current
      : {
        projectId: target.id,
        analysis: null,
        conversation: [],
        current_question: null,
        extractions: [],
        gaps: [],
        foundation: [],
        analysis_mode: null,
        analysis_notice: null,
      })
    setDevelopmentLoading(true)
    setDevelopmentStage('Checking the configured analysis provider…')
    setDevelopmentError('')
    window.clearTimeout(developmentStageTimer.current)
    developmentStageTimer.current = window.setTimeout(() => {
      if (
        developmentRequests.current.get(target.id) === target.premise
        && activeProjectId.current === target.id
      ) {
        setDevelopmentStage('Ollama is preparing or loading the model. You can keep writing while it works…')
      }
    }, 7_000)
    try {
      await api.analyzePremise(target.id)
      if (developmentRequests.current.get(target.id) !== target.premise) return
      setDevelopmentStage('Choosing one important clarification question…')
      const state = await api.nextPremiseQuestion(target.id)
      if (developmentRequests.current.get(target.id) === target.premise) {
        setDevelopment((current) => current?.projectId === target.id
          ? { ...state, projectId: target.id }
          : current)
      }
    } catch (reason) {
      if (developmentRequests.current.get(target.id) === target.premise) {
        setDevelopmentError(reason instanceof Error ? reason.message : 'Premise analysis could not be completed.')
      }
    } finally {
      if (developmentRequests.current.get(target.id) === target.premise) {
        developmentRequests.current.delete(target.id)
        if (activeProjectId.current === target.id) {
          window.clearTimeout(developmentStageTimer.current)
          setDevelopmentLoading(false)
          setDevelopmentStage('')
        }
      }
    }
  }, [])

  useEffect(() => {
    const initialize = async () => {
      try {
        await api.health()
        const [projects, savedTutorialState] = await Promise.all([
          api.listProjects(),
          api.getTutorialState(),
        ])
        setTutorialState(savedTutorialState)
        if (projects.length) {
          setProjects(projects)
          activeProjectId.current = projects[0].id
          setProject(projects[0])
          setDevelopmentProjectId(projects[0].id)
          const savedSetup = await api.getStorySetup(projects[0].id)
          setSetupState(savedSetup)
          setSetupIndex(firstOpenSetupQuestion(savedSetup.answers))
          const firstScene = flattenScenes(projects[0].acts)[0]
          setActiveSceneId(firstScene?.id ?? null)
          setOpenActs(projects[0].acts.map((act) => act.id))
          await refreshFacts(projects[0].id)
          if (savedSetup.step === 'complete' && !savedTutorialState.welcome_dismissed) {
            setShowWelcome(true)
          }
          if (projects[0].premise.trim()) {
            void runPremiseDevelopment(projects[0])
          }
        }
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : 'Unable to reach the local service.')
      } finally {
        setLoading(false)
      }
    }
    void initialize()
    return () => {
      window.clearTimeout(saveTimer.current)
      window.clearTimeout(developmentStageTimer.current)
      window.clearTimeout(assistantStageTimer.current)
    }
  }, [refreshFacts, runPremiseDevelopment])

  const acceptProject = useCallback((next: Project, preferredSceneId?: number, preserveScene = false) => {
    if (activeProjectId.current !== next.id) {
      setAssistantReply(null)
      setAssistantError('')
      setAssistantLoading(false)
      setAssistantStage('')
      window.clearTimeout(assistantStageTimer.current)
      setDevelopmentLoading(false)
      setDevelopmentStage('')
      window.clearTimeout(developmentStageTimer.current)
    }
    activeProjectId.current = next.id
    setProject(next)
    setProjects((current) => [next, ...current.filter((item) => item.id !== next.id)])
    const nextScenes = flattenScenes(next.acts)
    setActiveSceneId((current) => {
      const desiredScene = preserveScene ? current : preferredSceneId
      return desiredScene && nextScenes.some((scene) => scene.id === desiredScene)
        ? desiredScene
        : nextScenes[0]?.id ?? null
    })
    setOpenActs(next.acts.map((act) => act.id))
    setError('')
  }, [])

  const switchProject = async (projectId: number) => {
    const selected = projects.find((item) => item.id === projectId)
    if (!selected) return
    try {
      const savedSetup = await api.getStorySetup(selected.id)
      acceptProject(selected)
      setSetupState(savedSetup)
      setSetupIndex(firstOpenSetupQuestion(savedSetup.answers))
      setShowProjectSwitcher(false)
      await refreshFacts(selected.id)
      if (savedSetup.step === 'complete' && !tutorialState.welcome_dismissed) setShowWelcome(true)
      setPremiseAnswer('')
      if (selected.premise.trim()) void runPremiseDevelopment(selected)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not open this project.')
    }
  }

  const openProjectForm = (edit = false) => {
    setEditingProject(edit)
    setProjectForm(edit && project ? {
      title: project.title,
      format: project.format,
      genre: project.genre,
      runtime: project.runtime,
      language: project.language,
      premise: project.premise,
    } : blankProjectDetails)
    setShowProjectForm(true)
  }

  const createProject = async (sample = false) => {
    if (!sample) {
      openProjectForm(false)
      return
    }
    setCreating(true)
    try {
      const created = await api.createProject({
        title: 'The Last Message',
        format: 'Short Film',
        genre: 'Drama',
        runtime: '15 minutes',
        language: 'English',
        premise: 'A young woman discovers her brother is involved in a series of bank robberies.',
      })
      acceptProject(created)
      await refreshFacts(created.id)
      const savedSetup = await api.getStorySetup(created.id)
      setSetupState(savedSetup)
      if (!tutorialState.welcome_dismissed) setShowWelcome(true)
      void runPremiseDevelopment(created)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create project.')
    } finally {
      setCreating(false)
    }
  }

  const saveProjectDetails = async (event: React.FormEvent) => {
    event.preventDefault()
    setCreating(true)
    try {
      const next = editingProject && project
        ? await api.updateProject(project.id, projectForm)
        : await api.createProject({
          ...projectForm,
          title: projectForm.title.trim() || 'Untitled Screenplay',
          setup_flow: true,
        })
      if (!editingProject) setSetupState({ step: 'questions', answers: {} })
      acceptProject(next, editingProject ? activeScene?.id : undefined)
      await refreshFacts(next.id)
      setShowProjectForm(false)
      if (!editingProject) {
        const savedSetup = await api.getStorySetup(next.id)
        setSetupState(savedSetup)
        setSetupIndex(0)
        setSetupAnswer('')
        void runPremiseDevelopment(next)
      } else if (next.premise !== project?.premise) {
        void runPremiseDevelopment(next)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save project details.')
    } finally {
      setCreating(false)
    }
  }

  const persistSetup = async (next: StorySetupState) => {
    if (!project) return null
    try {
      const saved = await api.updateStorySetup(project.id, next)
      setSetupState(saved)
      return saved
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save Story Setup progress.')
      return null
    }
  }

  const saveSetupAnswer = async (status: StorySetupAnswer['status']) => {
    if (!project || !setupState) return
    const question = setupQuestions[setupIndex]
    if (!question || (status === 'answered' && !setupAnswer.trim())) return
    setSetupSaving(true)
    const response = status === 'answered' ? setupAnswer.trim() : ''
    const answers = {
      ...setupState.answers,
      [question.id]: { status, response },
    }
    const next: StorySetupState = { step: 'questions', answers }
    const savedSetup = await persistSetup(next)
    if (!savedSetup) {
      setSetupSaving(false)
      return
    }
    const savedStatus = savedSetup.answers[question.id].status

    try {
      const label = `${question.section}: ${question.label}`
      const existing = facts.find((fact) => fact.category === 'Story setup' && fact.label === label)
      if (savedStatus === 'answered') {
        const values = {
          category: 'Story setup',
          label,
          value: response,
          status: 'confirmed' as const,
          source: 'Writer',
          evidence: 'Writer-confirmed during guided Story Setup.',
          source_text: null,
          writer_confirmed: true,
          intentionally_undecided: false,
        }
        if (existing) {
          const updated = await api.updateFact(project.id, existing.id, values)
          setFacts((current) => current.map((fact) => fact.id === existing.id ? updated : fact))
        } else {
          const created = await api.createFact(project.id, values)
          setFacts((current) => [...current, created])
        }
      } else if (existing && savedStatus === 'skipped') {
        await api.deleteFact(project.id, existing.id)
        setFacts((current) => current.filter((fact) => fact.id !== existing.id))
      } else if (savedStatus === 'undecided') {
        const undecidedValues = {
          category: 'Story setup',
          label,
          value: response || 'Intentionally left undecided by the writer.',
          status: 'undecided',
          source: 'Writer',
          evidence: response
            ? `The writer chose not to decide this during guided Story Setup: ${response}`
            : 'The writer chose not to decide this during guided Story Setup.',
          writer_confirmed: false,
          intentionally_undecided: true,
        } as const
        if (existing) {
          const updated = await api.updateFact(project.id, existing.id, {
            ...undecidedValues,
            source_text: null,
          })
          setFacts((current) => current.map((fact) => fact.id === existing.id ? updated : fact))
        } else {
          const created = await api.createFact(project.id, undecidedValues)
          setFacts((current) => [...current, created])
        }
      }
      setFactHistory(await api.listFactHistory(project.id))
      setSetupAnswer('')
      const nextIndex = setupQuestions.findIndex((item, index) => index > setupIndex && !answers[item.id])
      if (nextIndex < 0) {
        await persistSetup({ ...next, step: 'review' })
      } else {
        setSetupIndex(nextIndex)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not sync this answer to the Story Bible.')
    } finally {
      setSetupSaving(false)
    }
  }

  const openSetupReview = async () => {
    if (!setupState) return
    await persistSetup({ ...setupState, step: 'review' })
  }

  const editSetupQuestion = async (questionId: string) => {
    const index = setupQuestions.findIndex((question) => question.id === questionId)
    if (index < 0 || !setupState) return
    setSetupIndex(index)
    setSetupAnswer(setupState.answers[questionId]?.response ?? '')
    await persistSetup({ ...setupState, step: 'questions' })
  }

  const completeSetup = async () => {
    if (!project || !setupState) return
    const completed = { ...setupState, step: 'complete' as const }
    if (!await persistSetup(completed)) return
    const next = { ...project, setup_step: 'complete' as const }
    acceptProject(next, activeScene?.id, true)
    if (!tutorialState.welcome_dismissed) setShowWelcome(true)
    else if (next.premise.trim()) void runPremiseDevelopment(next)
  }

  const reopenStorySetup = async () => {
    if (!project) return
    try {
      const saved = await api.getStorySetup(project.id)
      setSetupIndex(firstOpenSetupQuestion(saved.answers))
      await persistSetup({ ...saved, step: 'review' })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not reopen Story Setup.')
    }
  }

  const saveTutorialPreferences = useCallback(async (next: TutorialState) => {
    try {
      const saved = await api.updateTutorialState(next)
      setTutorialState(saved)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save tutorial preferences.')
    }
  }, [])

  const startTutorial = (tutorialId: string) => {
    setShowWelcome(false)
    setShowHelp(false)
    setContextualTip(null)
    setShowRightPanel(true)
    if (tutorialId === 'bible') setPanel('bible')
    else setPanel('assistant')
    setActiveTutorial(tutorialId)
    setTutorialIndex(0)
  }

  const offerContextualTip = (tipId: string) => {
    if (!tutorialState.completed[`tip:${tipId}`] && !tutorialState.completed[tipId]) {
      setContextualTip(tipId)
    }
  }

  const dismissContextualTip = (tipId: string) => {
    const next = {
      ...tutorialState,
      completed: { ...tutorialState.completed, [`tip:${tipId}`]: true },
    }
    void saveTutorialPreferences(next)
    setContextualTip(null)
  }

  const learnFromContextualTip = (tipId: string) => {
    dismissContextualTip(tipId)
    startTutorial(contextualTips[tipId].tutorial)
  }

  const exitTutorial = useCallback(() => {
    setActiveTutorial(null)
    setTourRect(null)
  }, [])

  const advanceTutorial = useCallback(() => {
    if (!activeTutorial) return
    const steps = tutorialSteps[activeTutorial] ?? []
    if (tutorialIndex + 1 < steps.length) {
      setTutorialIndex((index) => index + 1)
      return
    }
    const next = { ...tutorialState, completed: { ...tutorialState.completed, [activeTutorial]: true } }
    void saveTutorialPreferences(next)
    exitTutorial()
  }, [activeTutorial, exitTutorial, saveTutorialPreferences, tutorialIndex, tutorialState])

  const startWelcomeTour = () => {
    void saveTutorialPreferences({ ...tutorialState, welcome_dismissed: true })
    startTutorial('walkthrough')
  }

  useEffect(() => {
    if (!activeTutorial) return
    const targetSelector = tutorialSteps[activeTutorial]?.[tutorialIndex]?.target
    const target = targetSelector ? document.querySelector<HTMLElement>(targetSelector) : null
    if (!target) return
    target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    const updateRect = () => {
      const rect = target.getBoundingClientRect()
      setTourRect({ top: rect.top, left: rect.left, width: rect.width, height: rect.height })
    }
    const frame = window.requestAnimationFrame(updateRect)
    window.addEventListener('resize', updateRect)
    window.addEventListener('scroll', updateRect, true)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', updateRect)
      window.removeEventListener('scroll', updateRect, true)
    }
  }, [activeTutorial, panel, showRightPanel, tutorialIndex])

  useEffect(() => {
    if (!activeTutorial) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') exitTutorial()
      if (event.key === 'ArrowRight') advanceTutorial()
      if (event.key === 'ArrowLeft') setTutorialIndex((index) => Math.max(0, index - 1))
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeTutorial, advanceTutorial, exitTutorial, tutorialIndex])

  const persistScene = useCallback(async (sceneId: number, patch: Partial<Scene>) => {
    if (!project) return
    setSaveState('saving')
    try {
      const next = await api.updateScene(project.id, sceneId, {
        title: patch.title,
        description: patch.description,
        writer_notes: patch.writer_notes,
        completed: patch.completed,
        timeline_position: patch.timeline_position,
        timeline_context: patch.timeline_context,
        blocks: patch.blocks?.map(({ type, text, id }) => ({ id, type, text })),
      })
      acceptProject(next, sceneId, true)
      setSaveState('saved')
      setStatusMessage('All changes saved locally')
    } catch (reason) {
      setSaveState('error')
      setError(reason instanceof Error ? reason.message : 'Could not save this scene.')
    }
  }, [acceptProject, project])

  const scheduleSceneSave = (patch: Partial<Scene>) => {
    const currentScene = activeScene
    if (!currentScene) return
    setProject((current) => current ? ({
      ...current,
      acts: current.acts.map((act) => ({
        ...act,
        scenes: act.scenes.map((scene) => scene.id === currentScene.id ? { ...scene, ...patch } : scene),
      })),
    }) : current)
    setSaveState('saving')
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(() => {
      void persistScene(currentScene.id, patch)
    }, 550)
  }

  const updateBlock = (blockId: number, patch: Partial<ScreenplayBlock>) => {
    if (!activeScene) return
    const blocks = activeScene.blocks.map((block) => block.id === blockId ? { ...block, ...patch } : block)
    scheduleSceneSave({ blocks })
  }

  const addBlock = (type: BlockType) => {
    if (!activeScene) return
    scheduleSceneSave({ blocks: [...activeScene.blocks, emptyBlock(type, activeScene.blocks.length)] })
  }

  const removeBlock = (blockId: number) => {
    if (!activeScene) return
    scheduleSceneSave({ blocks: activeScene.blocks.filter((block) => block.id !== blockId) })
  }

  const mutateProject = async (action: () => Promise<Project>, preferredSceneId?: number) => {
    try {
      const next = await action()
      acceptProject(next, preferredSceneId)
      return true
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The requested change could not be saved.')
      return false
    }
  }

  const addAct = () => {
    if (project) void mutateProject(() => api.createAct(project.id))
  }

  const addScene = (actId: number) => {
    if (!project) return
    void mutateProject(() => api.createScene(project.id, actId)).then((created) => {
      if (created) offerContextualTip('scenes')
    })
  }

  const deleteScene = async (scene: Scene) => {
    if (!project || !window.confirm(`Delete "${scene.title}" and its contents? This cannot be undone.`)) return
    await mutateProject(() => api.deleteScene(project.id, scene.id))
  }

  const reorderScene = async (scene: Scene, direction: 'up' | 'down') => {
    if (project) await mutateProject(() => api.reorderScene(project.id, scene.id, direction), scene.id)
  }

  const moveScene = async (sceneId: number, targetActId: number, targetSceneId?: number) => {
    if (!project || sceneId === targetSceneId) return
    await mutateProject(
      () => api.moveScene(project.id, sceneId, { actId: targetActId, sceneId: targetSceneId }),
      sceneId,
    )
  }

  const runAssistant = async (prompt: string) => {
    if (!project || !prompt.trim()) return
    const requestProjectId = project.id
    failedAssistantPrompt.current = prompt
    setAssistantReply({ response: '', model: 'Ollama' })
    setAssistantLoading(true)
    setAssistantStage('Connecting to Ollama…')
    setAssistantError('')
    window.clearTimeout(assistantStageTimer.current)
    assistantStageTimer.current = window.setTimeout(() => {
      if (activeProjectId.current === requestProjectId) {
        setAssistantStage('Ollama is preparing or loading the model. Your screenplay remains editable…')
      }
    }, 7_000)
    try {
      const response = await api.askAIStream(
        requestProjectId,
        activeScene?.id ?? null,
        prompt,
        (content) => {
          if (activeProjectId.current !== requestProjectId) return
          setAssistantStage('Generating response…')
          setAssistantReply((current) => ({
            model: current?.model ?? 'Ollama',
            response: (current?.response ?? '') + content,
          }))
        },
      )
      if (activeProjectId.current === requestProjectId) {
        setAssistantReply(response)
        setAssistantPrompt((current) => current === prompt ? '' : current)
        failedAssistantPrompt.current = ''
      }
    } catch (reason) {
      if (activeProjectId.current === requestProjectId) {
        setAssistantError(reason instanceof Error ? reason.message : 'The local AI request failed.')
      }
    } finally {
      if (activeProjectId.current === requestProjectId) {
        window.clearTimeout(assistantStageTimer.current)
        setAssistantLoading(false)
        setAssistantStage('')
      }
    }
  }

  const submitAssistant = (event: React.FormEvent) => {
    event.preventDefault()
    void runAssistant(assistantPrompt.trim())
  }

  const resolvePremiseQuestion = async (status: 'answered' | 'skipped' | 'undecided' | 'not_applicable') => {
    if (!project || !development?.current_question) return
    if (status === 'answered' && !premiseAnswer.trim()) return
    setAnswerSaving(true)
    setDevelopmentError('')
    try {
      const state = await api.answerPremiseQuestion(
        project.id,
        development.current_question.id,
        status,
        premiseAnswer.trim(),
      )
      setDevelopment({ ...state, projectId: project.id })
      setPremiseAnswer('')
      await refreshFacts(project.id)
      if (!state.current_question) {
        const next = await api.nextPremiseQuestion(project.id)
        setDevelopment({ ...next, projectId: project.id })
      }
    } catch (reason) {
      setDevelopmentError(reason instanceof Error ? reason.message : 'Could not save your response.')
    } finally {
      setAnswerSaving(false)
    }
  }

  const askSetupFollowUp = async () => {
    if (!project || !project.premise.trim()) return
    setDevelopmentError('')
    try {
      const state = await api.nextPremiseQuestion(project.id)
      setDevelopment({ ...state, projectId: project.id })
    } catch (reason) {
      setDevelopmentError(reason instanceof Error ? reason.message : 'Could not generate an adaptive question.')
    }
  }

  const reopenPremiseQuestion = async (questionId: number) => {
    if (!project) return
    try {
      setDevelopmentError('')
      const state = await api.reopenPremiseQuestion(project.id, questionId)
      setDevelopment({ ...state, projectId: project.id })
    } catch (reason) {
      setDevelopmentError(reason instanceof Error ? reason.message : 'Could not reopen the question.')
    }
  }

  const updateNarrativeElement = async (
    key: PremiseElementKey,
    status: NarrativeStatus,
    value: string | null,
  ) => {
    if (!project) return
    try {
      setDevelopmentError('')
      const state = await api.updatePremiseElement(project.id, key, status, value)
      setDevelopment({ ...state, projectId: project.id })
      await refreshFacts(project.id)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Could not update this Story Bible entry.'
      setDevelopmentError(message)
      setError(message)
    }
  }

  const updateStoryFact = async (
    factId: number,
    values: Omit<StoryFact, 'id' | 'original_value' | 'modified_at'>,
  ): Promise<boolean> => {
    if (!project) return false
    try {
      const updated = await api.updateFact(project.id, factId, values)
      setFacts((current) => current.map((fact) => fact.id === factId ? updated : fact))
      setFactHistory(await api.listFactHistory(project.id))
      return true
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update this Story Bible entry.')
      return false
    }
  }

  const deleteStoryFact = async (factId: number) => {
    if (!project) return
    try {
      await api.deleteFact(project.id, factId)
      setFacts((current) => current.filter((fact) => fact.id !== factId))
      setFactHistory(await api.listFactHistory(project.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not delete the fact.')
    }
  }

  const addFact = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!project || !factForm.label.trim() || !factForm.value.trim()) return
    try {
      const fact = await api.createFact(project.id, {
        category: factForm.category,
        label: factForm.label.trim(),
        value: factForm.value.trim(),
        status: 'confirmed',
        source: 'Writer',
      })
      setFacts((current) => [...current, fact])
      setFactHistory(await api.listFactHistory(project.id))
      setFactForm({ label: '', value: '', category: 'Story fact' })
      setShowFactForm(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save this Story Bible entry.')
    }
  }

  const exportFountain = () => {
    if (!project) return
    const output = [
      `Title: ${project.title}`,
      `Credit: Written by`,
      '',
      ...project.acts.flatMap((act) => [
        `# ${act.title.toUpperCase()}`,
        '',
        ...act.scenes.flatMap((scene) => [
          scene.title.toUpperCase(),
          '',
          ...scene.blocks.filter((block) => block.type !== 'scene_heading').map((block) => {
            if (block.type === 'character') return `\n${block.text.toUpperCase()}`
            if (block.type === 'dialogue' || block.type === 'parenthetical') return block.text
            if (block.type === 'transition') return `>${block.text}`
            return block.text
          }),
          '',
        ]),
      ]),
    ].join('\n')
    saveText(`${project.title.replace(/[<>:"/\\|?*]+/g, '-')}.fountain`, output, 'text/plain')
  }

  const importFountain = async (file?: File) => {
    if (!file || !project) return
    try {
      const text = await file.text()
      const lines = text.split(/\r?\n/)
      const blocks: Array<{ type: BlockType; text: string }> = []
      for (const rawLine of lines) {
        const line = rawLine.trim()
        if (!line || /^Title:|^Credit:|^Author:|^Draft date:/i.test(line) || line.startsWith('#')) continue
        if (/^(INT\.|EXT\.|INT\/EXT\.)/i.test(line)) blocks.push({ type: 'scene_heading', text: line })
        else if (line.startsWith('>')) blocks.push({ type: 'transition', text: line.slice(1).trim() })
        else if (/^[A-Z][A-Z0-9 .()'-]{1,34}$/.test(line)) blocks.push({ type: 'character', text: line })
        else blocks.push({ type: 'action', text: line })
      }
      const sceneTitle = blocks.find((block) => block.type === 'scene_heading')?.text ?? 'INT. LOCATION - DAY'
      const preparedBlocks = blocks.length ? blocks : [{ type: 'action' as BlockType, text: text.trim() }]
      const next = await api.createScene(project.id, project.acts[0]?.id ?? (await api.createAct(project.id)).acts[0].id)
      const importedScene = flattenScenes(next.acts).find((scene) => scene.id !== activeSceneId)
      if (importedScene) {
        const updated = await api.updateScene(project.id, importedScene.id, {
          title: sceneTitle,
          description: `Imported from ${file.name}. Review imported formatting and mark facts as provisional.`,
          blocks: preparedBlocks,
        })
        acceptProject(updated, importedScene.id)
      } else {
        acceptProject(next)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not import this Fountain file.')
    }
  }

  const projectName = project?.title ?? 'SORKINS'
  const activeTourSteps = activeTutorial ? tutorialSteps[activeTutorial] ?? [] : []
  const activeTourStep = activeTourSteps[tutorialIndex]

  if (loading) {
    return <main className="loading-screen"><Film size={25} /><span>Opening your writing room…</span></main>
  }

  if (!project) {
    return (
      <main className="welcome-screen">
        <div className="welcome-brand"><span className="brand-mark"><Film size={19} /></span> SORKINS</div>
        <div className="welcome-card">
          <div className="welcome-kicker">A LOCAL SCREENWRITING STUDIO</div>
          <h1>Your story.<br /><span>Your call.</span></h1>
          <p>A quiet place to write, shape and keep track of your screenplay. Your projects stay on this computer.</p>
          {error && <div className="error-banner"><CircleHelp size={16} /> {error}</div>}
          <button className="primary-button welcome-create" onClick={() => void createProject()} disabled={creating}>
            <Plus size={17} /> Create a screenplay
          </button>
          <button className="text-button sample-button" onClick={() => void createProject(true)} disabled={creating}>
            Or open a sample project
          </button>
          <div className="local-note"><ShieldCheck size={15} /> Local-first · No account · AI is optional</div>
        </div>
        <span className="welcome-footer">WRITE WHAT ONLY YOU CAN WRITE</span>
        {showProjectForm && <ProjectFormModal
          values={projectForm}
          onChange={setProjectForm}
          onClose={() => setShowProjectForm(false)}
          onSubmit={(event) => void saveProjectDetails(event)}
          saving={creating}
          editing={false}
        />}
      </main>
    )
  }

  if (setupState && setupState.step !== 'complete') {
    return (
      <main className="app-shell setup-app">
        <header className="topbar">
          <div className="brand"><span className="brand-mark"><Film size={16} /></span><span>SORKINS</span></div>
          <div className="topbar-divider" />
          <strong className="setup-project-name">{project.title}</strong>
          <div className="topbar-spacer" />
          <span className={`save-indicator ${setupSaving ? 'saving' : ''}`}>{setupSaving ? <LoaderCircle size={13} className="spin" /> : <ShieldCheck size={13} />}<span>{setupSaving ? 'Saving progress' : 'Progress saved locally'}</span></span>
        </header>
        {error && <div className="global-error"><CircleHelp size={15} />{error}<button onClick={() => setError('')} aria-label="Dismiss error"><X size={15} /></button></div>}
        <StorySetupWizard
          project={project}
          state={setupState}
          questionIndex={setupIndex}
          answer={setupAnswer}
          saving={setupSaving}
          onAnswerChange={setSetupAnswer}
          onResolve={(status) => void saveSetupAnswer(status)}
          onEditQuestion={(questionId) => void editSetupQuestion(questionId)}
          onReview={() => void openSetupReview()}
          onComplete={() => void completeSetup()}
          onEditProject={() => openProjectForm(true)}
          development={currentDevelopment}
          developmentLoading={developmentLoading && developmentProjectId === project.id}
          developmentError={developmentProjectId === project.id ? developmentError : ''}
          adaptiveAnswer={premiseAnswer}
          adaptiveSaving={answerSaving}
          onAdaptiveAnswerChange={setPremiseAnswer}
          onAskAdaptive={() => void askSetupFollowUp()}
          onResolveAdaptive={(status) => void resolvePremiseQuestion(status)}
        />
        {showProjectForm && <ProjectFormModal
          values={projectForm}
          onChange={setProjectForm}
          onClose={() => setShowProjectForm(false)}
          onSubmit={(event) => void saveProjectDetails(event)}
          saving={creating}
          editing
        />}
      </main>
    )
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <button className="mobile-menu icon-button" aria-label="Toggle project navigation" onClick={() => setMobileNavOpen((open) => !open)}><Menu size={18} /></button>
        <div className="brand"><span className="brand-mark"><Film size={16} /></span><span>SORKINS</span></div>
        <div className="topbar-divider" />
        <div className="project-switch-wrap">
          <button className="project-title" onClick={() => setShowProjectSwitcher((open) => !open)}><span>{projectName}</span><ChevronDown size={14} /></button>
          {showProjectSwitcher && <div className="project-switcher">
            <span className="switcher-label">YOUR PROJECTS</span>
            {projects.map((item) => <button key={item.id} className={item.id === project.id ? 'current' : ''} onClick={() => void switchProject(item.id)}>{item.title}<small>{item.format}</small></button>)}
            <button className="switcher-new" onClick={() => { setShowProjectSwitcher(false); openProjectForm(false) }}><Plus size={14} /> New project</button>
          </div>}
        </div>
        <div className="topbar-meta">{project.format}{project.genre ? ` · ${project.genre}` : ''}</div>
        <div className="topbar-spacer" />
        <div className={`save-indicator ${saveState}`}>
          {saveState === 'saving' ? <LoaderCircle size={13} className="spin" /> : saveState === 'error' ? <CircleHelp size={13} /> : <Check size={13} />}
          <span>{saveState === 'saving' ? 'Saving' : saveState === 'error' ? 'Not saved' : statusMessage || 'Saved locally'}</span>
        </div>
        <button className="topbar-action" onClick={exportFountain}><Download size={15} /> <span>Export</span></button>
        <button className="topbar-action" onClick={() => window.print()} title="Print or save to PDF"><Printer size={15} /> <span>Print</span></button>
        <button className="topbar-action help-action" onClick={() => setShowHelp(true)}><CircleHelp size={15} /> <span>Learn</span></button>
        <button className="assistant-toggle icon-button" aria-label="Toggle writing assistant" onClick={() => setShowRightPanel((open) => !open)}><Sparkles size={16} /></button>
      </header>

      {error && <div className="global-error"><CircleHelp size={15} />{error}<button onClick={() => setError('')} aria-label="Dismiss error"><X size={15} /></button></div>}

      <div className="workspace">
        <aside className={`left-panel ${mobileNavOpen ? 'mobile-open' : ''}`}>
          <div className="panel-heading"><span>PROJECT</span><button className="icon-button subtle" aria-label="Project settings" onClick={() => openProjectForm(true)}><Settings2 size={15} /></button></div>
          <button className="project-card" data-tour="project" onClick={() => openProjectForm(true)}>
            <span className="project-icon"><Clapperboard size={16} /></span>
            <span className="project-card-copy"><strong>{project.title}</strong><small>{project.format}{project.runtime ? ` · ${project.runtime}` : ''}</small></span>
          </button>
          <div className="section-title"><span>STORY STRUCTURE</span><button className="add-small" onClick={addAct} title="Add act"><Plus size={15} /></button></div>
          <div className="outline" data-tour="outline">
            {project.acts.map((act) => (
              <ActOutline
                key={act.id}
                act={act}
                activeSceneId={activeScene?.id ?? null}
                expanded={openActs.includes(act.id)}
                onToggle={() => setOpenActs((current) => current.includes(act.id) ? current.filter((id) => id !== act.id) : [...current, act.id])}
                onSelect={(scene) => { setActiveSceneId(scene.id); setMobileNavOpen(false) }}
                onAddScene={() => addScene(act.id)}
                onDelete={deleteScene}
                onReorder={reorderScene}
                onMove={moveScene}
              />
            ))}
            {!project.acts.length && <div className="empty-outline">Add an act to start shaping your story.</div>}
          </div>
          <div className="left-panel-bottom">
            <button className="new-project-button" onClick={() => openProjectForm(false)}><Plus size={14} /> New project</button>
            <label className="import-button">
              <FilePlus2 size={15} /><span>Import Fountain / text</span>
              <input type="file" accept=".fountain,.txt,text/plain" onChange={(event) => void importFountain(event.target.files?.[0])} />
            </label>
            <div className="private-note"><ShieldCheck size={14} /><span>Your work is stored locally</span></div>
          </div>
        </aside>

        <section className="editor-panel" data-tour="editor">
          <div className="editor-toolbar">
            <div className="crumb"><span>SCREENPLAY</span><ChevronRight size={13} /><strong>{activeScene?.title ?? 'No scene selected'}</strong></div>
            <div className="toolbar-actions">
              <button className="editor-action" data-tour="notes" onClick={() => setShowNotes((value) => !value)}><BookOpen size={14} /><span>Scene notes</span></button>
              <button className={`complete-button ${activeScene?.completed ? 'complete' : ''}`} onClick={() => activeScene && scheduleSceneSave({ completed: !activeScene.completed })} disabled={!activeScene}>
                <Check size={14} /><span>{activeScene?.completed ? 'Completed' : 'Mark complete'}</span>
              </button>
            </div>
          </div>
          {showNotes && activeScene && (
            <div className="scene-note-fields">
              <label>Scene description<input value={activeScene.description} placeholder="What is already established about this scene?" onChange={(event) => scheduleSceneSave({ description: event.target.value })} /></label>
              <label>Story timeline position<input type="number" min="0" value={activeScene.timeline_position ?? ''} placeholder="Unspecified" onChange={(event) => scheduleSceneSave({ timeline_position: event.target.value === '' ? null : Number(event.target.value) })} /></label>
              <label>Timeline context<select value={activeScene.timeline_context} onChange={(event) => scheduleSceneSave({ timeline_context: event.target.value as Scene['timeline_context'] })}><option value="unspecified">Unspecified</option><option value="present">Present timeline</option><option value="flashback">Flashback</option><option value="dream">Dream</option><option value="alternate">Alternate timeline</option><option value="unreliable">Unreliable narration</option></select></label>
              <label>Private writer notes<textarea value={activeScene.writer_notes} placeholder="Your notes — not part of the screenplay" onChange={(event) => scheduleSceneSave({ writer_notes: event.target.value })} rows={2} /></label>
            </div>
          )}
          <div className="page-scroll">
            <article className="screenplay-page">
              {activeScene ? (
                <>
                  <div className="page-number">{pageCount}.</div>
                  <div className="scene-title-row">
                    <input className="scene-title-input" aria-label="Scene heading" value={activeScene.title} onChange={(event) => scheduleSceneSave({ title: event.target.value })} />
                    <button className="scene-menu-button" title="Delete scene" onClick={() => void deleteScene(activeScene)}><Trash2 size={15} /></button>
                  </div>
                  <div className="element-toolbar" data-tour="formatting">
                    <span>ELEMENT</span>
                    <div className="element-select-wrap">
                      <select aria-label="Add screenplay element" value="" onChange={(event) => { if (event.target.value) addBlock(event.target.value as BlockType) }}>
                        <option value="">Add an element…</option>
                        {blockTypes.map((type) => <option value={type.value} key={type.value}>{type.label}</option>)}
                      </select>
                      <ChevronDown size={13} />
                    </div>
                    <span className="element-hint">TAB to move between elements</span>
                  </div>
                  <div className="screenplay-content">
                    {activeScene.blocks.map((block, index) => (
                      <div className={`script-line ${block.type}`} key={block.id}>
                        <textarea
                          aria-label={`${blockLabel(block.type)} ${index + 1}`}
                          placeholder={block.type === 'action' ? 'Write action here…' : blockLabel(block.type)}
                          value={block.text}
                          rows={Math.max(1, block.text.split('\n').length)}
                          onChange={(event) => updateBlock(block.id, { text: event.target.value })}
                          onKeyDown={(event) => {
                            if (event.key === 'Tab' && !event.shiftKey && index < activeScene.blocks.length - 1) {
                              event.preventDefault()
                              document.querySelectorAll<HTMLTextAreaElement>('.script-line textarea')[index + 1]?.focus()
                            }
                          }}
                        />
                        <span className="line-type">{blockLabel(block.type)}</span>
                        <button className="remove-line" aria-label="Remove element" onClick={() => removeBlock(block.id)}><X size={13} /></button>
                      </div>
                    ))}
                    <button className="add-first-line" onClick={() => addBlock('action')}><Plus size={14} /> Add action</button>
                  </div>
                  <p className="page-end">— &nbsp; {project.title.toUpperCase()} &nbsp; —</p>
                </>
              ) : (
                <div className="no-scene"><Film size={25} /><h2>Your screenplay starts here</h2><p>Add an act and a scene from the project outline.</p></div>
              )}
            </article>
          </div>
          <footer className="editor-status">
            <div><span>SCENE {activeScene?.number ?? '—'}</span><span>{words} WORDS</span><span>{allScenes.length} SCENES</span></div>
            <div><span>APPROX. {pageCount} {pageCount === 1 ? 'PAGE' : 'PAGES'}</span><span>12 PT · COURIER</span></div>
          </footer>
        </section>

        <aside className={`right-panel ${showRightPanel ? 'mobile-visible' : ''}`} data-tour="assistant">
          <div className="assistant-header">
            <div className="assistant-title"><span className="sparkle-mark"><Sparkles size={15} /></span><div><strong>Writing room</strong><small>YOUR STORY, YOUR CALL</small></div></div>
          </div>
          <div className="tab-bar">
            <button className={panel === 'assistant' ? 'active' : ''} onClick={() => { setPanel('assistant'); offerContextualTip('assistant') }}><MessageSquareText size={14} /> Assistant</button>
            <button className={panel === 'bible' ? 'active' : ''} data-tour="story-bible" onClick={() => { setPanel('bible'); offerContextualTip('bible') }}><BookOpen size={14} /> Story Bible <span className="tab-count">{facts.length}</span></button>
          </div>
          {panel === 'assistant' ? (
            <div className="assistant-body">
              <div className="ai-notice"><ShieldCheck size={15} /><span>The assistant offers perspective. Your screenplay only changes when you do.</span></div>
              {project.premise.trim() && <StoryDevelopmentPanel
                premise={project.premise}
                development={currentDevelopment}
                loading={developmentLoading && developmentProjectId === project.id}
                stage={developmentStage}
                error={developmentProjectId === project.id ? developmentError : ''}
                answer={premiseAnswer}
                onAnswerChange={setPremiseAnswer}
                onResolve={(status) => void resolvePremiseQuestion(status)}
                onReopenQuestion={(questionId) => void reopenPremiseQuestion(questionId)}
                onRetry={() => void runPremiseDevelopment(project)}
                saving={answerSaving}
              />}
              <div className="assistant-context"><span className="context-label">CURRENT SCENE</span><strong>{activeScene?.title ?? 'No scene selected'}</strong><small>{activeScene ? `${activeScene.blocks.length} screenplay elements` : 'Choose a scene to add context'}</small></div>
              {assistantReply ? (
                <div className="assistant-reply">
                  <div className="reply-label"><Sparkles size={14} /> LOCAL ASSISTANT <span>{assistantReply.model}</span></div>
                  <p>{assistantReply.response}</p>
                  <button className="text-button" onClick={() => setAssistantReply(null)}>Clear response</button>
                </div>
              ) : (
                <div className="assistant-empty">
                  <div className="assistant-emblem"><Lightbulb size={21} /></div>
                  <strong>What would be useful?</strong>
                  <p>Ask about established story facts or a written scene. The assistant will ask when information is missing — it won't make story decisions for you.</p>
                  <div className="suggestion-list">
                    {['What information is still undecided?', 'Check this scene against established facts'].map((suggestion) => (
                      <button key={suggestion} onClick={() => setAssistantPrompt(suggestion)}>{suggestion}<ArrowRight size={13} /></button>
                    ))}
                  </div>
                </div>
              )}
              {assistantLoading && <div className="thinking"><LoaderCircle size={14} className="spin" />{assistantStage || 'Generating response…'}</div>}
              {assistantError && <div className="development-error"><CircleHelp size={13} /><span>{assistantError}</span><button onClick={() => void runAssistant(failedAssistantPrompt.current)}>Retry</button></div>}
              <form className="assistant-form" data-tour="assistant-input" onSubmit={(event) => void submitAssistant(event)}>
                <textarea value={assistantPrompt} onChange={(event) => setAssistantPrompt(event.target.value)} placeholder="Ask a question about your story…" rows={3} />
                <div className="assistant-form-footer"><span><ShieldCheck size={12} /> AI is optional and may be offline</span><button type="submit" className="send-button" aria-label="Send question" disabled={!assistantPrompt.trim() || assistantLoading}><Send size={15} /></button></div>
              </form>
              <div className="assistant-disclaimer">No dialogue analysis or screenplay rewriting. Suggestions always need your approval.</div>
            </div>
          ) : (
            <div className="bible-body" data-tour="bible-content">
              <div className="bible-intro"><BookOpen size={17} /><div><strong>Story Bible</strong><p>Writer-confirmed facts are the source of truth.</p></div></div>
              <button className="story-setup-reopen" onClick={() => void reopenStorySetup()}>Review Story Setup <ArrowRight size={13} /></button>
              {project.premise && <div className="premise-card"><span>PREMISE <span className="status-pill confirmed">CONFIRMED</span></span><p>{project.premise}</p></div>}
              {currentDevelopment?.analysis && <NarrativeBibleEditor
                analysis={currentDevelopment.analysis}
                onSave={(key, status, value) => updateNarrativeElement(key, status, value)}
              />}
              <StoryBibleStructured projectId={project.id} />
              <div className="fact-heading" id="general-story-facts"><span>GENERAL STORY FACTS</span><button className="add-small" onClick={() => setShowFactForm((value) => !value)} title="Add a fact"><Plus size={15} /></button></div>
              {showFactForm && (
                <form className="fact-form" onSubmit={(event) => void addFact(event)}>
                  <input value={factForm.label} onChange={(event) => setFactForm({ ...factForm, label: event.target.value })} placeholder="Fact name" aria-label="Fact name" required />
                  <textarea value={factForm.value} onChange={(event) => setFactForm({ ...factForm, value: event.target.value })} placeholder="What has the writer established?" aria-label="Fact" rows={3} required />
                  <div><button type="button" className="text-button" onClick={() => setShowFactForm(false)}>Cancel</button><button type="submit" className="primary-button compact"><Save size={13} /> Save fact</button></div>
                </form>
              )}
              <div className="fact-list">
                {facts.map((fact) => (
                  <StoryFactCard
                    key={`${fact.id}:${fact.label}:${fact.value}:${fact.status}`}
                    fact={fact}
                    onSave={(values) => updateStoryFact(fact.id, values)}
                    onDelete={() => void deleteStoryFact(fact.id)}
                  />
                ))}
                {!facts.length && !project.premise && <div className="fact-empty">No story facts yet. Add information as you decide it; nothing is assumed on your behalf.</div>}
              </div>
              {factHistory.length > 0 && (
                <details className="fact-history">
                  <summary>Decision history <span>{factHistory.length}</span></summary>
                  {factHistory.map((revision) => (
                    <div className="fact-history-item" key={revision.id}>
                      <span className="status-pill">{revision.action}</span>
                      <strong>{revision.label}</strong>
                      <p>{revision.value}</p>
                      <small>{new Date(revision.changed_at).toLocaleString()} · {revision.source}</small>
                    </div>
                  ))}
                </details>
              )}
              <div className="bible-footer"><ShieldCheck size={13} /> AI inferences never become confirmed facts automatically.</div>
            </div>
          )}
          <div className="right-panel-footer"><span><span className="online-dot" /> LOCAL PROJECT</span><span>PRIVATE BY DESIGN</span></div>
        </aside>
      </div>
      <div className="bottom-hints"><span>AUTO-SAVE ON</span><span>MADE FOR THE PAGE</span><span>{project.language || 'English'}</span></div>
      {contextualTip && contextualTips[contextualTip] && (
        <aside className="contextual-tip" role="note" aria-label="First-time feature tip">
          <div><strong>{contextualTips[contextualTip].title}</strong><p>{contextualTips[contextualTip].description}</p></div>
          <div>
            <button className="text-button" onClick={() => dismissContextualTip(contextualTip)}>Dismiss</button>
            <button className="primary-button compact" onClick={() => learnFromContextualTip(contextualTip)}>Show guide</button>
          </div>
        </aside>
      )}
      {showProjectForm && <ProjectFormModal
        values={projectForm}
        onChange={setProjectForm}
        onClose={() => setShowProjectForm(false)}
        onSubmit={(event) => void saveProjectDetails(event)}
        saving={creating}
        editing={editingProject}
      />}
      {showWelcome && (
        <div className="modal-backdrop">
          <section className="welcome-onboarding" role="dialog" aria-modal="true" aria-labelledby="first-visit-title">
            <span className="welcome-kicker">WELCOME TO SORKINS</span>
            <h2 id="first-visit-title">A writing room that keeps the story yours.</h2>
            <p>Sorkins helps you organise a screenplay, keep track of story facts, and explore narrative questions. Its local AI can offer analysis and technical suggestions; it does not write your screenplay or make creative decisions for you.</p>
            <label className="dont-show-option"><input type="checkbox" checked={dontShowWelcome} onChange={(event) => setDontShowWelcome(event.target.checked)} /> Don't show this again</label>
            <div className="onboarding-actions">
              <button className="text-button" onClick={() => {
                setShowWelcome(false)
                if (dontShowWelcome) {
                  void saveTutorialPreferences({ ...tutorialState, welcome_dismissed: true })
                }
              }}>Explore on my own</button>
              <button className="primary-button" onClick={startWelcomeTour}><Sparkles size={15} /> Start guided tour</button>
            </div>
          </section>
        </div>
      )}
      {showHelp && (
        <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowHelp(false) }}>
          <section className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="help-title">
            <div className="modal-heading">
              <div><span className="welcome-kicker">LEARN SORKINS</span><h2 id="help-title">Guides and walkthroughs</h2></div>
              <button className="icon-button" aria-label="Close help" onClick={() => setShowHelp(false)}><X size={17} /></button>
            </div>
            {[
              ['walkthrough', 'Application walkthrough', 'Tour the project, scenes, editor, Story Bible, assistant, and notes.'],
              ['editor', 'Screenplay editor', 'Learn the editor and its screenplay formatting controls.'],
              ['bible', 'Story Bible', 'Review confirmed facts, inferences, and undecided details.'],
              ['assistant', 'AI assistant', 'Learn how the local assistant uses project context.'],
              ['scenes', 'Scene management', 'Explore acts, scenes, and scene notes.'],
            ].map(([id, title, description]) => (
              <button className="help-topic" key={id} onClick={() => startTutorial(id)}>
                <span><strong>{title}</strong><small>{description}</small></span>
                <span className="help-topic-status">{tutorialState.completed[id] ? 'Replay' : 'Start'} <ArrowRight size={13} /></span>
              </button>
            ))}
            <p className="help-footnote">These guides use controls that exist in the current app. A dedicated continuity-analysis tool is not available yet.</p>
          </section>
        </div>
      )}
      {activeTutorial && (
        <div className="tutorial-layer">
          {tourRect && <div className="tour-spotlight" style={{
            top: tourRect.top - 5,
            left: tourRect.left - 5,
            width: tourRect.width + 10,
            height: tourRect.height + 10,
          }} />}
          <section
            className="tour-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tour-step-title"
            style={tourRect ? {
              top: Math.min(tourRect.top + tourRect.height + 14, window.innerHeight - 230),
              left: Math.max(12, Math.min(tourRect.left, window.innerWidth - 360)),
            } : undefined}
          >
            <div className="tour-card-heading">
              <span className="welcome-kicker">{activeTutorial.replace('-', ' ')} · {tutorialIndex + 1}/{activeTourSteps.length}</span>
              <button className="icon-button" aria-label="Exit tour" onClick={exitTutorial}><X size={16} /></button>
            </div>
            <h2 id="tour-step-title">{activeTourStep?.title}</h2>
            <p>{activeTourStep?.description}</p>
            <div className="tour-actions">
              <button className="text-button" onClick={exitTutorial}>Exit tour</button>
              <span>
                <button className="text-button" disabled={tutorialIndex === 0} onClick={() => setTutorialIndex((index) => Math.max(0, index - 1))}>Previous</button>
                <button className="primary-button compact" onClick={advanceTutorial}>{tutorialIndex + 1 === activeTourSteps.length ? 'Finish' : 'Next'} <ArrowRight size={13} /></button>
              </span>
            </div>
          </section>
        </div>
      )}
    </main>
  )
}

function StorySetupWizard(props: {
  project: Project
  state: StorySetupState
  questionIndex: number
  answer: string
  saving: boolean
  onAnswerChange: (value: string) => void
  onResolve: (status: StorySetupAnswer['status']) => void
  onEditQuestion: (questionId: string) => void
  onReview: () => void
  onComplete: () => void
  onEditProject: () => void
  development: PremiseDevelopment | null
  developmentLoading: boolean
  developmentError: string
  adaptiveAnswer: string
  adaptiveSaving: boolean
  onAdaptiveAnswerChange: (value: string) => void
  onAskAdaptive: () => void
  onResolveAdaptive: (status: 'answered' | 'skipped' | 'undecided' | 'not_applicable') => void
}) {
  const {
    project, state, questionIndex, answer, saving, onAnswerChange, onResolve, onEditQuestion,
    onReview, onComplete, onEditProject, development, developmentLoading, developmentError,
    adaptiveAnswer, adaptiveSaving, onAdaptiveAnswerChange, onAskAdaptive, onResolveAdaptive,
  } = props
  const question = setupQuestions[questionIndex] ?? setupQuestions[0]
  const isReview = state.step === 'review'
  const established = setupQuestions.filter((item) => state.answers[item.id]?.status === 'answered').length
  const foundationStatus = (id: string) => {
    const answer = state.answers[id]
    return answer?.status === 'answered'
      ? 'Established'
      : answer?.status === 'skipped'
        ? 'Deferred'
        : answer?.status === 'undecided'
          ? 'Undecided'
          : 'Open'
  }
  const sections = [...new Set(setupQuestions.map((item) => item.section))]

  return (
    <section className="setup-shell">
      <div className="setup-wrap">
        <div className="setup-step-labels">
          <span className="done"><Check size={13} /> Project details</span>
          <span className={!isReview ? 'active' : 'done'}>{!isReview ? '02' : <Check size={13} />} Guided development</span>
          <span className={isReview ? 'active' : ''}>{isReview ? '03' : '03'} Story foundation</span>
        </div>
        {isReview ? (
          <div className="setup-review">
            <div className="setup-review-heading">
              <span className="welcome-kicker">YOUR STORY FOUNDATION</span>
              <h1>Review what you know so far.</h1>
              <p>These are your decisions, not requirements. Anything open or deferred can be revisited later.</p>
            </div>
            <div className="setup-overview">
              <div>
                <span className="setup-card-kicker">PROJECT OVERVIEW</span>
                <h2>{project.title}</h2>
                <p>{project.premise || 'Premise not set yet.'}</p>
                <small>{[project.format, project.genre || 'Genre undecided'].filter(Boolean).join(' · ')}</small>
              </div>
              <button className="text-button" onClick={onEditProject}>Edit project details</button>
            </div>
            <div className="foundation-status-grid">
              {foundationFields.map(([id, title]) => (
                <div className={`foundation-status ${foundationStatus(id).toLowerCase()}`} key={id}>
                  <span>{title}</span><strong>{foundationStatus(id)}</strong>
                </div>
              ))}
            </div>
            {project.premise.trim() && (
              <section className="adaptive-follow-up">
                <div className="adaptive-follow-up-heading">
                  <div><span className="setup-card-kicker">OPTIONAL FOUNDATION FOLLOW-UP</span><p>A locally selected question based on open story foundations and your saved answers.</p></div>
                  <span className="setup-fallback-label">Deterministic selection</span>
                </div>
                {developmentLoading && !development?.analysis && <p className="adaptive-status">Preparing the existing narrative analysis…</p>}
                {developmentError && <p className="adaptive-error">{developmentError}</p>}
                {development?.current_question ? (
                  <div className="adaptive-question">
                    <strong>{development.current_question.question}</strong>
                    <textarea aria-label="Adaptive follow-up answer" value={adaptiveAnswer} onChange={(event) => onAdaptiveAnswerChange(event.target.value)} placeholder="Answer, leave it undecided, or skip…" rows={3} maxLength={2_000} />
                    <div className="adaptive-question-actions">
                      <button className="text-button" disabled={adaptiveSaving} onClick={() => onResolveAdaptive('undecided')}>I haven't decided</button>
                      <button className="text-button" disabled={adaptiveSaving} onClick={() => onResolveAdaptive('skipped')}>Skip for now</button>
                      <button className="primary-button compact" disabled={adaptiveSaving || !adaptiveAnswer.trim()} onClick={() => onResolveAdaptive('answered')}>{adaptiveSaving ? 'Saving…' : 'Save answer'}</button>
                    </div>
                  </div>
                ) : development?.analysis && development.gaps.length === 0 ? (
                  <p className="adaptive-status">No additional question is currently prioritized. You can proceed or revisit this later.</p>
                ) : (
                  <button className="adaptive-start" disabled={developmentLoading || !development?.analysis} onClick={onAskAdaptive}>
                    {developmentLoading ? 'Preparing a question…' : 'Ask one follow-up question'} <ArrowRight size={14} />
                  </button>
                )}
                <p className="adaptive-disclaimer">Question selection uses local rules and does not represent semantic AI analysis.</p>
              </section>
            )}
            <div className="setup-review-groups">
              {sections.map((section) => (
                <section className="setup-review-group" key={section}>
                  <h2>{section}</h2>
                  {setupQuestions.filter((item) => item.section === section).map((item) => {
                    const itemAnswer = state.answers[item.id]
                    const status = itemAnswer?.status === 'answered'
                      ? 'Writer-confirmed'
                      : itemAnswer?.status === 'skipped'
                        ? 'Intentionally deferred'
                        : itemAnswer?.status === 'undecided'
                          ? 'Undecided'
                          : 'Not covered'
                    return (
                      <div className="setup-review-row" key={item.id}>
                        <div>
                          <span className="setup-review-status">{status}</span>
                          <strong>{item.label}</strong>
                          <p>{itemAnswer?.status === 'answered'
                            ? itemAnswer.response
                            : itemAnswer?.status === 'skipped'
                              ? 'Skipped for now; no story fact was added.'
                              : itemAnswer?.status === 'undecided'
                                ? 'The writer chose to leave this open.'
                                : 'Not answered yet.'}</p>
                        </div>
                        <button className="text-button" onClick={() => onEditQuestion(item.id)}>Edit</button>
                      </div>
                    )
                  })}
                </section>
              ))}
            </div>
            <div className="setup-review-footer">
              <button className="text-button" onClick={() => onEditQuestion(setupQuestions[0].id)}>Back to questions</button>
              <div><span>{established} answers saved to your Story Bible</span><button className="primary-button" onClick={onComplete}><Check size={15} /> Confirm & enter screenplay</button></div>
            </div>
          </div>
        ) : (
          <>
            <div className="setup-progress">
              <div><span>STORY FOUNDATIONS</span><strong>{established} of {setupQuestions.length} questions answered</strong></div>
              <div className="setup-progress-track"><span style={{ width: `${Math.round((questionIndex / setupQuestions.length) * 100)}%` }} /></div>
              <div className="setup-foundation-chips">
                {foundationFields.map(([id, title]) => <span key={id} className={foundationStatus(id).toLowerCase()}>{title}: {foundationStatus(id)}</span>)}
              </div>
            </div>
            <article className="setup-question-card">
              <div className="setup-question-meta"><span>{question.section}</span><span>{questionIndex + 1} / {setupQuestions.length}</span></div>
              <h1>{question.title}</h1>
              <p>{question.explanation}</p>
              {question.options ? (
                <label className="setup-answer-label">{question.label}
                  <select value={answer} onChange={(event) => onAnswerChange(event.target.value)}>
                    <option value="">Choose if you know, or skip for now…</option>
                    {question.options.map((option) => <option key={option}>{option}</option>)}
                  </select>
                </label>
              ) : (
                <label className="setup-answer-label">{question.label}
                  <textarea autoFocus value={answer} onChange={(event) => onAnswerChange(event.target.value)} placeholder="Write what you know so far…" rows={5} maxLength={5_000} />
                </label>
              )}
              {state.answers[question.id] && <span className="setup-saved-hint">Previous response saved · You can change it here</span>}
              <div className="setup-question-actions">
                <button className="text-button setup-previous" disabled={questionIndex === 0 || saving} onClick={() => onEditQuestion(setupQuestions[questionIndex - 1].id)}>Previous</button>
                <button className="text-button" disabled={saving} onClick={() => onResolve('undecided')}>I haven't decided</button>
                <button className="text-button" disabled={saving} onClick={() => onResolve('skipped')}>Skip for now</button>
                <button className="primary-button" disabled={saving || !answer.trim()} onClick={() => onResolve('answered')}>{saving ? 'Saving…' : 'Continue'} <ArrowRight size={15} /></button>
              </div>
            </article>
            <button className="setup-review-link" onClick={onReview}>Review your story foundation <ArrowRight size={14} /></button>
          </>
        )}
      </div>
    </section>
  )
}

function NarrativeBibleEditor(props: {
  analysis: NonNullable<PremiseDevelopment['analysis']>
  onSave: (key: PremiseElementKey, status: NarrativeStatus, value: string | null) => Promise<void>
}) {
  const entries = Object.entries(props.analysis.narrative_elements) as [
    PremiseElementKey,
    NonNullable<PremiseDevelopment['analysis']>['narrative_elements'][PremiseElementKey],
  ][]
  return (
    <section className="narrative-bible">
      <div className="narrative-overview-heading"><span>PREMISE ANALYSIS</span><span>Writer-editable</span></div>
      <p className="narrative-bible-note">Review each value, evidence, and confidence. Changes here update the Story Bible.</p>
      {entries.map(([key, element]) => (
        <NarrativeBibleItem
          key={`${key}:${element.status}:${element.value ?? ''}`}
          elementKey={key}
          value={element.value}
          status={element.status}
          evidence={element.evidence}
          explanation={element.explanation}
          confidence={element.confidence}
          writerConfirmed={element.writer_confirmed}
          intentionallyUndecided={element.intentionally_undecided}
          antagonistClassification={key === 'antagonist'
            ? antagonistClassificationLabels[props.analysis.antagonist_classification]
            : undefined}
          onSave={props.onSave}
        />
      ))}
    </section>
  )
}

function StoryFactCard(props: {
  fact: StoryFact
  onSave: (values: Omit<StoryFact, 'id' | 'original_value' | 'modified_at'>) => Promise<boolean>
  onDelete: () => void
}) {
  const { fact, onSave, onDelete } = props
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState(fact.label)
  const [value, setValue] = useState(fact.value)
  const [status, setStatus] = useState<StoryFact['status']>(fact.status)
  const [saving, setSaving] = useState(false)

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!label.trim() || !value.trim()) return
    setSaving(true)
    try {
      const saved = await onSave({
        category: fact.category,
        label: label.trim(),
        value: value.trim(),
        status,
        source: fact.source,
        evidence: fact.evidence,
        source_text: fact.source_text,
        writer_confirmed: status === 'confirmed',
        intentionally_undecided: fact.intentionally_undecided,
      })
      if (saved) setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fact-card">
      <div>
        <span className="fact-category">{fact.category}</span>
        <span className={`status-pill ${fact.status}`}>{fact.status}</span>
        {!editing && <button className="text-button" onClick={() => setEditing(true)}>Edit</button>}
        <button className="fact-delete" aria-label={`Delete ${fact.label}`} onClick={onDelete}><X size={13} /></button>
      </div>
      {editing ? (
        <form className="fact-form" onSubmit={(event) => void save(event)}>
          <input value={label} onChange={(event) => setLabel(event.target.value)} aria-label="Story fact name" required />
          <textarea value={value} onChange={(event) => setValue(event.target.value)} aria-label="Story fact value" rows={3} required />
          <label>Status
            <select value={status} onChange={(event) => setStatus(event.target.value as StoryFact['status'])}>
              <option value="confirmed">Writer-confirmed</option>
              <option value="inferred">Inferred</option>
              <option value="provisional">Provisional</option>
              <option value="undecided">Undecided</option>
            </select>
          </label>
          <div>
            <button type="button" className="text-button" onClick={() => setEditing(false)}>Cancel</button>
            <button type="submit" className="save-bible-element" disabled={saving}>
              <Save size={12} /> {saving ? 'Saving…' : 'Save entry'}
            </button>
          </div>
        </form>
      ) : (
        <>
          <strong>{fact.label}</strong>
          <p>{fact.value}</p>
          {fact.evidence && <small className="bible-element-evidence">{fact.evidence}</small>}
        </>
      )}
    </div>
  )
}

function NarrativeBibleItem(props: {
  elementKey: PremiseElementKey
  value: string | null
  status: NarrativeStatus
  evidence: string
  explanation: string
  confidence: number
  writerConfirmed: boolean
  intentionallyUndecided: boolean
  antagonistClassification?: string
  onSave: (key: PremiseElementKey, status: NarrativeStatus, value: string | null) => Promise<void>
}) {
  const {
    elementKey, value, status, evidence, explanation, confidence, writerConfirmed,
    intentionallyUndecided, antagonistClassification, onSave,
  } = props
  const [draftValue, setDraftValue] = useState(value ?? '')
  const [draftStatus, setDraftStatus] = useState<NarrativeStatus>(status)
  const [saving, setSaving] = useState(false)
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setSaving(true)
    try {
      await onSave(
        elementKey,
        draftStatus,
        draftStatus === 'EXPLICIT' || draftStatus === 'INFERRED' ? draftValue.trim() : null,
      )
    } finally {
      setSaving(false)
    }
  }
  return (
    <details className="bible-narrative-item">
      <summary>
        <span>{premiseElementLabels[elementKey]}</span>
        <span className={`status-pill ${status.toLowerCase()}`}>{status.replace('_', ' ')}</span>
      </summary>
      {antagonistClassification && <p className="bible-element-evidence">{antagonistClassification}</p>}
      <p className="bible-element-evidence">{evidence}</p>
      <p className="bible-element-evidence">{explanation} · Confidence {Math.round(confidence * 100)}%</p>
      {writerConfirmed && <span className="status-pill confirmed">WRITER CONFIRMED</span>}
      {intentionallyUndecided && <span className="status-pill undecided">INTENTIONALLY UNDECIDED</span>}
      <form onSubmit={(event) => void save(event)}>
        {(draftStatus === 'EXPLICIT' || draftStatus === 'INFERRED') && (
          <label>Story detail<input value={draftValue} onChange={(event) => setDraftValue(event.target.value)} maxLength={2_000} required /></label>
        )}
        <label>Status
          <select value={draftStatus} onChange={(event) => {
            const next = event.target.value as NarrativeStatus
            setDraftStatus(next)
            if (next === 'UNDECIDED' || next === 'NOT_APPLICABLE') setDraftValue('')
          }}>
            <option value="EXPLICIT">Explicit / writer-confirmed</option>
            <option value="INFERRED">Inferred / provisional</option>
            <option value="UNDECIDED">Undecided</option>
            <option value="NOT_APPLICABLE">Not applicable</option>
          </select>
        </label>
        <button type="submit" className="save-bible-element" disabled={saving}>
          <Save size={12} /> {saving ? 'Saving…' : 'Save entry'}
        </button>
      </form>
    </details>
  )
}

function StoryDevelopmentPanel(props: {
  premise: string
  development: PremiseDevelopment | null
  loading: boolean
  stage: string
  error: string
  answer: string
  onAnswerChange: (value: string) => void
  onResolve: (status: 'answered' | 'skipped' | 'undecided' | 'not_applicable') => void
  onReopenQuestion: (questionId: number) => void
  onRetry: () => void
  saving: boolean
}) {
  const {
    premise, development, loading, stage, error, answer, onAnswerChange,
    onResolve, onReopenQuestion, onRetry, saving,
  } = props
  const elements = development?.analysis?.narrative_elements
  const entries = elements ? Object.entries(elements) as [
    PremiseElementKey,
    NonNullable<PremiseDevelopment['analysis']>['narrative_elements'][PremiseElementKey],
  ][] : []
  const explicitCount = entries.filter(([, element]) => element.status === 'EXPLICIT').length
  const inferredCount = entries.filter(([, element]) => element.status === 'INFERRED').length
  const undecidedCount = entries.filter(([, element]) => element.status === 'UNDECIDED').length
  const notApplicableCount = entries.filter(([, element]) => element.status === 'NOT_APPLICABLE').length
  const gaps = development?.gaps ?? entries
    .filter(([, element]) => element.status === 'INFERRED' || element.status === 'UNDECIDED')
    .map(([key]) => ({ element_key: key, importance: 'OPTIONAL' as const }))
  const previousQuestions = development?.conversation.filter((question) => question.status !== 'pending') ?? []
  const question = development?.current_question

  return (
    <section className="story-development">
      <div className="development-heading">
        <div><Sparkles size={14} /><strong>Story development</strong></div>
        <button className="development-retry" onClick={onRetry} disabled={loading} title="Analyze or resume premise questions">
          {loading ? <LoaderCircle size={13} className="spin" /> : <RotateCcw size={13} />}
          {loading ? 'Working…' : elements ? 'Refresh' : 'Analyze'}
        </button>
      </div>
      <div className="development-premise"><span>WRITER'S PREMISE</span><p>{premise}</p></div>
      {development?.analysis && <p className="deterministic-mode-label">{development.analysis_mode === 'deterministic' ? 'RULE-BASED OFFLINE ANALYSIS · NO SEMANTIC AI' : 'AI ANALYSIS · FACTS REQUIRE WRITER REVIEW'} · QUESTION SELECTION IS DETERMINISTIC</p>}
      {error && <div className="development-error"><CircleHelp size={13} /><span>{error}</span><button onClick={onRetry} disabled={loading}>Retry</button></div>}
      {development?.analysis_notice && <p className="development-empty">{development.analysis_notice}</p>}
      {loading && !elements && <div className="development-wait"><LoaderCircle size={15} className="spin" /> {stage || 'Analyzing the premise… You can keep writing while this runs.'}</div>}
      {!loading && !elements && !error && <p className="development-empty">Analyze the premise to identify what it establishes and what remains open.</p>}
      {elements && (
        <>
          <div className="development-progress">
            <div className="development-progress-copy">
              <span>{explicitCount} explicit</span><span>{inferredCount} inferred</span><span>{undecidedCount} undecided</span><span>{notApplicableCount} not applicable</span>
            </div>
            <p>This tracks information only—not story quality. Inferences are not confirmed facts.</p>
          </div>
          {development?.foundation.length > 0 && (
            <div className="foundation-assessment">
              <div className="narrative-overview-heading"><span>STORY FOUNDATION</span><span>Informational, not a score</span></div>
              {development.foundation.map((item) => (
                <div className="foundation-assessment-item" key={item.key}>
                  <div><strong>{item.label}</strong><span className={`foundation-assessment-status ${item.status}`}>{item.status.replaceAll('_', ' ')}</span></div>
                  <p>{item.explanation}</p>
                  {item.next_consideration && <small>To consider: {item.next_consideration}</small>}
                </div>
              ))}
            </div>
          )}
          <div className="missing-information">
            <div className="narrative-overview-heading"><span>OPEN QUESTIONS</span><span>{gaps.length}</span></div>
            {gaps.length
              ? <p>{gaps.map((gap) => `${gap.importance}: ${premiseElementLabels[gap.element_key]}`).join(' · ')}</p>
              : <p>No elements currently need clarification.</p>}
          </div>
          {development?.extractions.length > 0 && (
            <details className="narrative-overview">
              <summary className="narrative-overview-heading">
                <span>LITERAL PREMISE EXTRACTION</span><span>{development.extractions.length} spans</span>
              </summary>
              {development.extractions.map((item, index) => (
                <div className="narrative-element" key={`${item.category}:${item.value}:${index}`}>
                  <span className="context-label">{item.category.replace('_', ' ').toUpperCase()} · EXPLICIT</span>
                  <p className="narrative-value">{item.value}</p>
                  <p className="narrative-evidence">{item.evidence}</p>
                  <small className="narrative-evidence">SOURCE: {item.source} · {item.extraction_method.toUpperCase()} · {item.confirmation_status.replace('_', ' ').toUpperCase()}{item.source_start !== null && item.source_end !== null ? ` · CHARACTERS ${item.source_start}–${item.source_end}` : ''}</small>
                </div>
              ))}
            </details>
          )}
          {question ? (
            <div className="premise-question">
              <span className="context-label">ONE QUESTION AT A TIME · {premiseElementLabels[question.element_key].toUpperCase()}</span>
              <strong>{question.question}</strong>
              <textarea value={answer} onChange={(event) => onAnswerChange(event.target.value)} placeholder="Your answer — or leave it undecided" rows={2} />
              <div className="question-actions">
                <button className="answer-button" onClick={() => onResolve('answered')} disabled={saving || !answer.trim()}>{saving ? 'Saving…' : 'Save answer'}</button>
                <button onClick={() => onResolve('skipped')} disabled={saving}>Skip</button>
                <button onClick={() => onResolve('undecided')} disabled={saving}>Leave undecided</button>
                <button onClick={() => onResolve('not_applicable')} disabled={saving}>Not applicable</button>
              </div>
            </div>
          ) : (
            <div className="no-premise-question">
              {loading
                ? 'Choosing one important clarification question…'
                : gaps.length
                  ? 'You have deferred the remaining gaps. Continue writing or reopen a skipped question from the conversation history.'
                  : 'No clarification questions are needed right now.'}
            </div>
          )}
          <details className="narrative-overview">
            <summary className="narrative-overview-heading"><span>NARRATIVE OVERVIEW</span><span>{entries.length} elements</span></summary>
            {entries.map(([key, element]) => (
                  <details className="narrative-element" key={key}>
                    <summary>
                      <span>{premiseElementLabels[key]}</span>
                      <span className={`status-pill ${element.status.toLowerCase()}`}>{element.status.replace('_', ' ')}</span>
                    </summary>
                    {key === 'antagonist' && (
                      <p className="narrative-classification">
                        {antagonistClassificationLabels[development?.analysis?.antagonist_classification ?? 'undecided']}
                      </p>
                    )}
                    <p className="narrative-evidence">SOURCE: {element.source}</p>
                    <p className="narrative-value">{element.value ?? 'Not established yet'}</p>
                    <p className="narrative-evidence">{element.evidence}</p>
                    <p className="narrative-evidence">{element.explanation} · Confidence {Math.round(element.confidence * 100)}%</p>
                    {element.writer_confirmed && <span className="status-pill confirmed">WRITER CONFIRMED</span>}
                    {element.intentionally_undecided && <span className="status-pill undecided">INTENTIONALLY UNDECIDED</span>}
                  </details>
            ))}
          </details>
          {previousQuestions.length > 0 && (
            <details className="question-history">
              <summary>Conversation history <span>{previousQuestions.length}</span></summary>
              {previousQuestions.map((item) => (
                <div className="question-history-item" key={item.id}>
                  <span className="status-pill">{item.status}</span>
                  {item.premise_snapshot !== premise && <small>From an earlier premise version</small>}
                  <strong>{item.question}</strong>
                  {item.response && <p>{item.response}</p>}
                  {(item.status === 'skipped' || item.status === 'undecided' || item.status === 'not_applicable') && (
                    <button className="reopen-question" onClick={() => onReopenQuestion(item.id)}>Ask again</button>
                  )}
                </div>
              ))}
            </details>
          )}
        </>
      )}
    </section>
  )
}

function ProjectFormModal(props: {
  values: ProjectDetails
  onChange: (values: ProjectDetails) => void
  onClose: () => void
  onSubmit: (event: React.FormEvent) => void
  saving: boolean
  editing: boolean
}) {
  const { values, onChange, onClose, onSubmit, saving, editing } = props
  const update = (key: keyof ProjectDetails, value: string) => onChange({ ...values, [key]: value })
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <form className="project-modal" onSubmit={onSubmit}>
        <div className="modal-heading"><div><span className="welcome-kicker">{editing ? 'PROJECT DETAILS' : 'A NEW WRITING PROJECT'}</span><h2>{editing ? 'Project details' : 'Start with what you know.'}</h2></div><button type="button" className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={17} /></button></div>
        <label>Project title<input autoFocus required maxLength={200} value={values.title} onChange={(event) => update('title', event.target.value)} placeholder="Untitled Screenplay" /></label>
        <div className="form-grid">
          <label>Format<select value={values.format} onChange={(event) => update('format', event.target.value)}><option>Feature Film</option><option>Short Film</option><option>Series</option><option>Television</option><option>Web Series</option></select></label>
          <label>Genre<input value={values.genre} onChange={(event) => update('genre', event.target.value)} placeholder="Optional" /></label>
          <label>Intended runtime<input value={values.runtime} onChange={(event) => update('runtime', event.target.value)} placeholder="e.g. 100 minutes" /></label>
          <label>Language<input value={values.language} onChange={(event) => update('language', event.target.value)} placeholder="English" /></label>
        </div>
        <label>Premise<textarea rows={3} value={values.premise} onChange={(event) => update('premise', event.target.value)} placeholder="A starting point, if you have one. You can decide later." /></label>
        <div className="modal-footer"><span>Optional details can be changed whenever you like.</span><button type="submit" className="primary-button" disabled={saving}>{saving ? 'Saving…' : editing ? 'Save details' : 'Create project'}</button></div>
      </form>
    </div>
  )
}

function ActOutline(props: {
  act: Act
  activeSceneId: number | null
  expanded: boolean
  onToggle: () => void
  onSelect: (scene: Scene) => void
  onAddScene: () => void
  onDelete: (scene: Scene) => void
  onReorder: (scene: Scene, direction: 'up' | 'down') => void
  onMove: (sceneId: number, targetActId: number, targetSceneId?: number) => void
}) {
  const { act, activeSceneId, expanded, onToggle, onSelect, onAddScene, onDelete, onReorder, onMove } = props
  const [draggedSceneId, setDraggedSceneId] = useState<number | null>(null)
  const [dropTarget, setDropTarget] = useState<number | null>(null)
  return (
    <div className="act-group">
      <div
        className={`act-row ${draggedSceneId ? 'drop-act' : ''}`}
        onDragOver={(event) => { if (event.dataTransfer.types.includes('text/plain')) event.preventDefault() }}
        onDrop={(event) => {
          event.preventDefault()
          const movedSceneId = Number(event.dataTransfer.getData('text/plain')) || draggedSceneId
          if (movedSceneId) onMove(movedSceneId, act.id)
          setDraggedSceneId(null)
        }}
      >
        <button className="act-toggle" onClick={onToggle}>{expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}<span>{act.title}</span><small>{act.scenes.length}</small></button>
        <button className="add-small act-add" title={`Add scene to ${act.title}`} onClick={onAddScene}><Plus size={14} /></button>
      </div>
      {expanded && act.scenes.map((scene, index) => (
        <div
          className={`scene-row ${scene.id === activeSceneId ? 'selected' : ''} ${dropTarget === scene.id ? 'drop-target' : ''}`}
          key={scene.id}
          draggable
          onDragStart={(event) => {
            setDraggedSceneId(scene.id)
            event.dataTransfer.effectAllowed = 'move'
            event.dataTransfer.setData('text/plain', String(scene.id))
          }}
          onDragEnd={() => { setDraggedSceneId(null); setDropTarget(null) }}
          onDragOver={(event) => {
            if (event.dataTransfer.types.includes('text/plain') && draggedSceneId !== scene.id) {
              event.preventDefault()
              setDropTarget(scene.id)
            }
          }}
          onDrop={(event) => {
            event.preventDefault()
            event.stopPropagation()
            const draggedId = Number(event.dataTransfer.getData('text/plain')) || draggedSceneId
            if (draggedId) onMove(draggedId, act.id, scene.id)
            setDraggedSceneId(null)
            setDropTarget(null)
          }}
        >
          <button className="scene-select" onClick={() => onSelect(scene)}>
            <span className={`scene-status ${scene.completed ? 'done' : ''}`}>{scene.completed ? <Check size={10} /> : scene.number}</span>
            <span className="scene-row-title">{scene.title}</span>
          </button>
          <div className="scene-row-actions">
            <button aria-label="Move scene up" onClick={() => onReorder(scene, 'up')} disabled={index === 0}><ArrowUp size={12} /></button>
            <button aria-label="Move scene down" onClick={() => onReorder(scene, 'down')} disabled={index === act.scenes.length - 1}><ArrowDown size={12} /></button>
            <button aria-label="Delete scene" onClick={() => onDelete(scene)}><Trash2 size={12} /></button>
          </div>
        </div>
      ))}
      {expanded && !act.scenes.length && <button className="empty-act" onClick={onAddScene}><Plus size={12} /> Add first scene</button>}
    </div>
  )
}

export default App
