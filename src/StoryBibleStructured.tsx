import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from './api'
import type { ContinuityFinding, StoryEntity, StoryEntityKind, StoryEntityRevision } from './types'

const sections: Array<{ kind: StoryEntityKind; label: string; title: string }> = [
  { kind: 'characters', label: 'Characters', title: 'Character' },
  { kind: 'relationships', label: 'Relationships', title: 'Relationship' },
  { kind: 'conflicts', label: 'Conflicts', title: 'Conflict' },
  { kind: 'locations', label: 'Locations', title: 'Location' },
  { kind: 'events', label: 'Events & Timeline', title: 'Story event' },
]
const blank = (): Record<string, unknown> => ({
  source_type: 'writer', confirmation_status: 'writer_confirmed', evidence: '', source_text: '', source_refs: [],
  name: '', aliases: [], description: '', role: '', goals: '', motivations: '', fears: '', strengths: '', weaknesses: '', character_arc: '', current_status: 'unknown', status_effective_position: null,
  character_a_id: null, character_b_id: null, relationship_type: 'unspecified',
  conflict_type: 'unspecified', status: 'active', character_ids: [], objectives: [], stakes: '',
  parent_location_id: null, characteristics: [], location_id: null, timeline_position: null, date_text: '', related_event_ids: [], dependency_event_ids: [],
})
const numberList = (value: unknown): number[] => Array.isArray(value) ? value.map(Number).filter(Number.isFinite) : []
const stringList = (value: unknown): string[] => Array.isArray(value) ? value.map(String) : []
const displayName = (entity: StoryEntity): string => String(entity.name ?? entity.description ?? `Item ${entity.id}`)
const titleField = (kind: StoryEntityKind): string => kind === 'characters' || kind === 'locations' ? 'name' : kind === 'relationships' ? 'relationship_type' : 'description'

export function StoryBibleStructured({ projectId }: { projectId: number }) {
  const [kind, setKind] = useState<StoryEntityKind>('characters')
  const [entities, setEntities] = useState<Record<StoryEntityKind, StoryEntity[]>>({ characters: [], relationships: [], conflicts: [], locations: [], events: [] })
  const [findings, setFindings] = useState<ContinuityFinding[]>([])
  const [history, setHistory] = useState<StoryEntityRevision[]>([])
  const [draft, setDraft] = useState<Record<string, unknown>>(blank)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [explainingId, setExplainingId] = useState<number | null>(null)
  const [explanation, setExplanation] = useState('')

  const records = entities[kind]
  const load = useCallback(async () => {
    try {
      const [characterRows, relationshipRows, conflictRows, locationRows, eventRows, revisions, savedFindings] = await Promise.all([
        api.listStoryEntities(projectId, 'characters'),
        api.listStoryEntities(projectId, 'relationships'),
        api.listStoryEntities(projectId, 'conflicts'),
        api.listStoryEntities(projectId, 'locations'),
        api.listStoryEntities(projectId, 'events'),
        api.listStoryEntityHistory(projectId),
        api.listContinuityFindings(projectId),
      ])
      setEntities({ characters: characterRows, relationships: relationshipRows, conflicts: conflictRows, locations: locationRows, events: eventRows })
      setHistory(revisions)
      setFindings(savedFindings)
      setError('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load Story Bible data.') }
    finally { setLoading(false) }
  }, [projectId])
  useEffect(() => { void Promise.resolve().then(load) }, [load])

  const related = entities
  const setField = (field: string, value: unknown) => setDraft((current) => ({ ...current, [field]: value }))
  const textField = (field: string) => String(draft[field] ?? '')
  const selectedIds = (field: string) => numberList(draft[field])

  const beginEdit = (record: StoryEntity) => {
    setEditingId(record.id)
    setDraft({ ...blank(), ...record, character_ids: record.character_ids ?? (Array.isArray(record.characters) ? (record.characters as Array<{ id: number }>).map((character) => character.id) : []) })
    setError('')
  }
  const cancelEdit = () => { setEditingId(null); setDraft(blank()) }

  const payload = (): Record<string, unknown> => {
    const provenance = {
      source_type: textField('source_type'), confirmation_status: textField('confirmation_status'),
      evidence: textField('evidence'), source_text: textField('source_text') || null,
      source_refs: Array.isArray(draft.source_refs) ? draft.source_refs : [],
    }
    if (kind === 'characters') return { ...provenance, name: textField('name').trim(), aliases: stringList(draft.aliases), description: textField('description'), role: textField('role'), goals: textField('goals'), motivations: textField('motivations'), fears: textField('fears'), strengths: textField('strengths'), weaknesses: textField('weaknesses'), character_arc: textField('character_arc'), current_status: textField('current_status'), status_effective_position: draft.status_effective_position === '' || draft.status_effective_position == null ? null : Number(draft.status_effective_position) }
    if (kind === 'relationships') return { ...provenance, character_a_id: Number(draft.character_a_id), character_b_id: Number(draft.character_b_id), relationship_type: textField('relationship_type'), description: textField('description') }
    if (kind === 'conflicts') return { ...provenance, description: textField('description').trim(), conflict_type: textField('conflict_type'), status: textField('status'), character_ids: selectedIds('character_ids'), objectives: stringList(draft.objectives), stakes: textField('stakes') }
    if (kind === 'locations') return { ...provenance, name: textField('name').trim(), description: textField('description'), aliases: stringList(draft.aliases), parent_location_id: draft.parent_location_id == null || draft.parent_location_id === '' ? null : Number(draft.parent_location_id), characteristics: stringList(draft.characteristics) }
    return { ...provenance, description: textField('description').trim(), character_ids: selectedIds('character_ids'), location_id: draft.location_id == null || draft.location_id === '' ? null : Number(draft.location_id), timeline_position: draft.timeline_position == null || draft.timeline_position === '' ? null : Number(draft.timeline_position), date_text: textField('date_text') || null, related_event_ids: selectedIds('related_event_ids'), dependency_event_ids: selectedIds('dependency_event_ids') }
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true); setError('')
    try {
      if (editingId == null) await api.createStoryEntity(projectId, kind, payload())
      else await api.updateStoryEntity(projectId, kind, editingId, payload())
      cancelEdit()
      await load()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not save this item.') }
    finally { setSaving(false) }
  }

  const remove = async (record: StoryEntity) => {
    if (!window.confirm(`Delete “${displayName(record)}”? Any links to this entity may be removed.`)) return
    setSaving(true); setError('')
    try { await api.deleteStoryEntity(projectId, kind, record.id); if (editingId === record.id) cancelEdit(); await load() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not delete this item.') }
    finally { setSaving(false) }
  }

  const analyze = async () => {
    setAnalyzing(true); setError('')
    try { const result = await api.analyzeContinuity(projectId); setFindings(result.findings) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Continuity review failed.') }
    finally { setAnalyzing(false) }
  }
  const saveDisposition = async (finding: ContinuityFinding, disposition: ContinuityFinding['disposition'], note: string) => {
    setSaving(true); setError('')
    try {
      const updated = await api.updateContinuityFinding(projectId, finding.id, disposition, note)
      setFindings((current) => current.map((item) => item.id === updated.id ? updated : item))
      setExplainingId(null); setExplanation('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not save the review decision.') }
    finally { setSaving(false) }
  }

  const changeKind = (next: StoryEntityKind) => { setKind(next); cancelEdit(); setError('') }
  const titleKey = titleField(kind)

  return <section className="structured-bible" aria-label="Structured Story Bible">
    <h3>Story Bible</h3>
    <nav className="structured-tabs" aria-label="Story Bible sections">
      {sections.map((item) => <button type="button" key={item.kind} className={kind === item.kind ? 'active' : ''} aria-pressed={kind === item.kind} onClick={() => changeKind(item.kind)}>{item.label}</button>)}
      <button type="button" onClick={() => document.getElementById('general-story-facts')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>General facts</button>
    </nav>

    <form className="structured-form" onSubmit={(event) => void save(event)}>
      <h4>{editingId == null ? `Add ${sections.find((item) => item.kind === kind)?.title.toLowerCase()}` : `Edit ${sections.find((item) => item.kind === kind)?.title.toLowerCase()}`}</h4>
      <div className="structured-fields">
        {kind === 'characters' && <>
          <Field label="Name" value={textField('name')} onChange={(value) => setField('name', value)} required />
          <Field label="Description / background" value={textField('description')} onChange={(value) => setField('description', value)} multiline />
          <Field label="Role or narrative function (optional)" value={textField('role')} onChange={(value) => setField('role', value)} />
          <Field label="Aliases, comma separated" value={stringList(draft.aliases).join(', ')} onChange={(value) => setField('aliases', value.split(',').map((item) => item.trim()).filter(Boolean))} />
          <Field label="Goals" value={textField('goals')} onChange={(value) => setField('goals', value)} multiline />
          <Field label="Motivations" value={textField('motivations')} onChange={(value) => setField('motivations', value)} multiline />
          <Field label="Fears" value={textField('fears')} onChange={(value) => setField('fears', value)} multiline />
          <Field label="Strengths" value={textField('strengths')} onChange={(value) => setField('strengths', value)} multiline />
          <Field label="Weaknesses" value={textField('weaknesses')} onChange={(value) => setField('weaknesses', value)} multiline />
          <Field label="Character arc" value={textField('character_arc')} onChange={(value) => setField('character_arc', value)} multiline />
          <label className="structured-field">Current status<select value={textField('current_status')} onChange={(event) => setField('current_status', event.target.value)}><option value="unknown">Unknown / unspecified</option><option value="alive">Alive</option><option value="dead">Dead</option><option value="missing">Missing</option><option value="other">Other</option></select></label>
          <Field label="Status effective timeline position (optional)" type="number" value={textField('status_effective_position')} onChange={(value) => setField('status_effective_position', value === '' ? null : Number(value))} />
        </>}

        {kind === 'relationships' && <>
          <EntitySelector label="Character A" options={related.characters} selected={draft.character_a_id == null ? [] : [Number(draft.character_a_id)]} multiple={false} onChange={(ids) => setField('character_a_id', ids[0] ?? null)} empty="Add at least two characters first." />
          <EntitySelector label="Character B" options={related.characters.filter((item) => item.id !== Number(draft.character_a_id))} selected={draft.character_b_id == null ? [] : [Number(draft.character_b_id)]} multiple={false} onChange={(ids) => setField('character_b_id', ids[0] ?? null)} empty="Choose a different character." />
          <Field label="Relationship type" value={textField('relationship_type')} onChange={(value) => setField('relationship_type', value)} placeholder="e.g. siblings, colleagues, unspecified" />
          <Field label="Description" value={textField('description')} onChange={(value) => setField('description', value)} multiline />
        </>}

        {kind === 'conflicts' && <>
          <Field label="Conflict description" value={textField('description')} onChange={(value) => setField('description', value)} multiline required />
          <label className="structured-field">Conflict type<select value={textField('conflict_type')} onChange={(event) => setField('conflict_type', event.target.value)}>{['unspecified', 'internal', 'interpersonal', 'societal', 'environmental', 'organisational', 'other'].map((value) => <option key={value}>{value}</option>)}</select></label>
          <label className="structured-field">Current status<select value={textField('status')} onChange={(event) => setField('status', event.target.value)}>{['active', 'paused', 'resolved', 'unknown'].map((value) => <option key={value}>{value}</option>)}</select></label>
          <EntitySelector label="Involved characters (optional)" options={related.characters} selected={selectedIds('character_ids')} onChange={(ids) => setField('character_ids', ids)} empty="No characters yet; you can save a conflict without linking one." />
          <Field label="Objectives (one per line)" value={stringList(draft.objectives).join('\n')} onChange={(value) => setField('objectives', value.split('\n').map((item) => item.trim()).filter(Boolean))} multiline />
          <Field label="Stakes" value={textField('stakes')} onChange={(value) => setField('stakes', value)} multiline />
        </>}

        {kind === 'locations' && <>
          <Field label="Location name" value={textField('name')} onChange={(value) => setField('name', value)} required />
          <Field label="Description / relevant notes" value={textField('description')} onChange={(value) => setField('description', value)} multiline />
          <Field label="Aliases, comma separated" value={stringList(draft.aliases).join(', ')} onChange={(value) => setField('aliases', value.split(',').map((item) => item.trim()).filter(Boolean))} />
          <EntitySelector label="Parent location (optional)" options={related.locations.filter((item) => item.id !== editingId)} selected={draft.parent_location_id == null ? [] : [Number(draft.parent_location_id)]} multiple={false} onChange={(ids) => setField('parent_location_id', ids[0] ?? null)} empty="No other locations available." />
          <Field label="Characteristics (one per line)" value={stringList(draft.characteristics).join('\n')} onChange={(value) => setField('characteristics', value.split('\n').map((item) => item.trim()).filter(Boolean))} multiline />
        </>}

        {kind === 'events' && <>
          <Field label="Event title or description" value={textField('description')} onChange={(value) => setField('description', value)} multiline required />
          <EntitySelector label="Characters involved" options={related.characters} selected={selectedIds('character_ids')} onChange={(ids) => setField('character_ids', ids)} empty="No characters yet; an event can be saved without links." />
          <EntitySelector label="Location (optional)" options={related.locations} selected={draft.location_id == null ? [] : [Number(draft.location_id)]} multiple={false} onChange={(ids) => setField('location_id', ids[0] ?? null)} empty="No locations available." />
          <Field label="Timeline position (optional)" type="number" value={textField('timeline_position')} onChange={(value) => setField('timeline_position', value === '' ? null : Number(value))} />
          <Field label="Approximate or exact date (optional)" value={textField('date_text')} onChange={(value) => setField('date_text', value)} placeholder="Writer-specified wording" />
          <EntitySelector label="Related events" options={related.events.filter((item) => item.id !== editingId)} selected={selectedIds('related_event_ids')} onChange={(ids) => setField('related_event_ids', ids)} empty="No other events yet." />
          <EntitySelector label="Depends on these events" options={related.events.filter((item) => item.id !== editingId)} selected={selectedIds('dependency_event_ids')} onChange={(ids) => setField('dependency_event_ids', ids)} empty="No other events yet." />
        </>}

        <Field label="Evidence" value={textField('evidence')} onChange={(value) => setField('evidence', value)} multiline />
        <Field label="Source text (optional)" value={textField('source_text')} onChange={(value) => setField('source_text', value)} multiline />
        <label className="structured-field">Source type<select value={textField('source_type')} onChange={(event) => setField('source_type', event.target.value)}>{[['writer', 'Writer'], ['premise', 'Premise'], ['screenplay', 'Screenplay'], ['ai_inference', 'AI inference']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="structured-field">Confirmation<select value={textField('confirmation_status')} onChange={(event) => setField('confirmation_status', event.target.value)}>{[['writer_confirmed', 'Writer confirmed'], ['explicit_unconfirmed', 'Explicit, unconfirmed'], ['inferred_unconfirmed', 'Inferred, unconfirmed'], ['undecided', 'Undecided']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      {textField('confirmation_status') !== 'writer_confirmed' && <p className="structured-note">This entry remains unconfirmed and will not be treated as established continuity.</p>}
      <div className="structured-form-actions"><button className="primary-button compact" disabled={saving || loading}>{saving ? 'Saving…' : editingId == null ? 'Add item' : 'Save changes'}</button>{editingId != null && <button type="button" className="text-button" onClick={cancelEdit}>Cancel</button>}<span aria-live="polite">{!saving && !loading && 'Changes are saved to this project.'}</span></div>
    </form>

    {error && <p className="development-error" role="alert">{error}</p>}
    {loading ? <p className="fact-empty" role="status">Loading Story Bible…</p> : <div className="structured-list">{records.map((record) => {
      const revisions = history.filter((revision) => revision.entity_type === kind.slice(0, -1) && revision.entity_id === record.id)
      return <article key={record.id} className="structured-record">
        <div className="structured-record-heading"><strong>{displayName(record)}</strong><span className="status-pill">{String(record.confirmation_status).replaceAll('_', ' ')}</span></div>
        <p>{String(record.description ?? record.evidence ?? 'No description provided.')}</p>
        <small>{String(record.source_type)} source{record.evidence ? ` · Evidence: ${String(record.evidence)}` : ''}</small>
        <div className="structured-record-actions"><button type="button" className="text-button" onClick={() => beginEdit(record)}>Edit</button><button type="button" className="text-button" disabled={saving} onClick={() => void remove(record)}>Delete</button></div>
        {revisions.length > 0 && <details><summary>Revision history ({revisions.length})</summary>{revisions.map((revision) => <p key={revision.id}><strong>{revision.action}</strong> · {new Date(revision.changed_at).toLocaleString()} · {String(revision.snapshot[titleKey] ?? revision.snapshot.name ?? revision.snapshot.description ?? '')}</p>)}</details>}
      </article>
    })}{records.length === 0 && <p className="fact-empty">No {sections.find((item) => item.kind === kind)?.label.toLowerCase()} yet. The story can remain undecided while you write.</p>}</div>}

    <div className="continuity-box">
      <div><strong>Continuity review</strong><button type="button" className="add-small" onClick={() => void analyze()} disabled={analyzing || loading}>{analyzing ? 'Checking…' : 'Analyze completed scenes'}</button></div>
      {findings.map((finding) => <article key={finding.id} className={`continuity-finding ${finding.resolution_status}`}>
        <strong>{finding.severity}: {finding.description}</strong>
        <small>Confidence {Math.round(finding.confidence * 100)}% · Scene IDs: {finding.relevant_scene_ids.join(', ') || 'none'} · {finding.resolution_status}</small>
        {finding.evidence_refs.map((evidence, index) => <p key={index}>{String(evidence.label ?? evidence.kind)}: {String(evidence.text ?? '')}</p>)}
        {finding.writer_explanation && <p className="writer-explanation">Writer’s explanation: {finding.writer_explanation}</p>}
        <small>Current disposition: {finding.disposition.replaceAll('_', ' ')}</small>
        {explainingId === finding.id ? <form onSubmit={(event) => { event.preventDefault(); void saveDisposition(finding, 'explained', explanation) }}><Field label="Explanation" value={explanation} onChange={setExplanation} multiline required /><button className="primary-button compact" disabled={saving || !explanation.trim()}>Save explanation</button><button type="button" className="text-button" onClick={() => setExplainingId(null)}>Cancel</button></form> : <div className="finding-actions">
          <button type="button" className="text-button" disabled={saving} onClick={() => void saveDisposition(finding, 'accepted_intentional', finding.writer_explanation)}>Accept as intentional</button>
          <button type="button" className="text-button" disabled={saving} onClick={() => { setExplainingId(finding.id); setExplanation(finding.writer_explanation) }}>Explain</button>
          <button type="button" className="text-button" disabled={saving} onClick={() => void saveDisposition(finding, 'dismissed', finding.writer_explanation)}>Dismiss</button>
          <button type="button" className="text-button" disabled={saving} onClick={() => void saveDisposition(finding, 'needs_correction', finding.writer_explanation)}>Mark for correction</button>
        </div>}
      </article>)}
      {findings.length === 0 && <p role="status">{loading ? 'Loading saved continuity findings…' : 'No saved continuity findings. Run a review when you are ready.'}</p>}
      <small>Analysis is opt-in, uses confirmed entities and explicit timeline positions, and never edits screenplay text.</small>
    </div>
  </section>
}

function Field({ label, value, onChange, multiline = false, required = false, type = 'text', placeholder }: { label: string; value: string; onChange: (value: string) => void; multiline?: boolean; required?: boolean; type?: string; placeholder?: string }) {
  return <label className="structured-field">{label}{multiline ? <textarea value={value} onChange={(event) => onChange(event.target.value)} required={required} placeholder={placeholder} rows={2} /> : <input type={type} value={value} onChange={(event) => onChange(event.target.value)} required={required} placeholder={placeholder} />}</label>
}

function EntitySelector({ label, options, selected, onChange, multiple = true, empty }: { label: string; options: StoryEntity[]; selected: number[]; onChange: (ids: number[]) => void; multiple?: boolean; empty: string }) {
  const [query, setQuery] = useState('')
  const available = options.filter((item) => displayName(item).toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  const toggle = (id: number) => {
    if (multiple) onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id])
    else onChange(selected.includes(id) ? [] : [id])
  }
  return <fieldset className="entity-selector"><legend>{label}</legend>
    {selected.length > 0 && <div className="selected-entities">{selected.map((id) => { const item = options.find((option) => option.id === id); return <button type="button" key={id} aria-label={`Remove ${item ? displayName(item) : `item ${id}`}`} onClick={() => toggle(id)}>{item ? displayName(item) : `Missing item ${id}`} ×</button> })}</div>}
    {options.length === 0 ? <small>{empty}</small> : <><input aria-label={`Search ${label}`} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${label.toLowerCase()}…`} /><div className="entity-options">{available.map((item) => <label key={item.id}><input type={multiple ? 'checkbox' : 'radio'} checked={selected.includes(item.id)} onChange={() => toggle(item.id)} />{displayName(item)}</label>)}{available.length === 0 && <small>No matching project records.</small>}</div></>}
  </fieldset>
}
