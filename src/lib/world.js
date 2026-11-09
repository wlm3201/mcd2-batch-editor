function objectField(parent, key) {
  if (parent[key] === undefined) parent[key] = {}
  const value = parent[key]
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error(key + ': invalid save object')
  return value
}

function arrayField(parent, key) {
  if (parent[key] === undefined) parent[key] = []
  if (!Array.isArray(parent[key])) throw new Error(key + ': invalid save list')
  return parent[key]
}

function checkFormat(state, data) {
  const actual = state.doc?.SerializeMeta
  for (const key of ['HardFormat', 'SoftVersion', 'FormatHash']) {
    const expected = data?.saveFormat?.[key]
    if (
      expected !== undefined &&
      actual?.[key] !== undefined &&
      String(actual[key]) !== String(expected)
    )
      throw new Error('World actions need a matching save-format diff: ' + key)
  }
}

function indexed(records, key) {
  const result = new Map()
  for (const record of records) {
    if (!record || typeof record[key] !== 'string' || result.has(record[key]))
      throw new Error('Invalid or duplicate ' + key)
    result.set(record[key], record)
  }
  return result
}

function atLeast(record, field, target) {
  const current = Number(String(record[field] ?? 0))
  if (Number.isNaN(current) || !Number.isFinite(target) || target < 0)
    throw new Error(field + ': invalid progress')
  if (record[field] == null || current < target) {
    record[field] = target
    return true
  }
  return false
}

function questNames(data, field) {
  const names = data?.[field]
  if (
    !Array.isArray(names) ||
    !names.length ||
    names.some((name) => !Array.isArray(data.quests?.[name]))
  )
    throw new Error('Missing game quest data: ' + field)
  return names
}

function finishQuests(state, data, names) {
  const section = objectField(state.body, 'quest')
  const records = arrayField(section, 'Quests')
  const existing = indexed(records, 'QuestName')
  let changed = 0,
    added = 0
  for (const name of names) {
    let quest = existing.get(name)
    if (!quest) {
      quest = { QuestName: name, State: 'Completed', TaskData: [] }
      records.push(quest)
      added++
    }
    let edited = quest.State !== 'Completed'
    quest.State = 'Completed'
    const tasks = arrayField(quest, 'TaskData')
    const byName = indexed(tasks, 'TaskName')
    for (const id of data.quests[name]) {
      let task = byName.get(id)
      if (!task) {
        task = { TaskName: id, State: 'Completed', PartialProgress: 0 }
        tasks.push(task)
        edited = true
      }
      if (task.State !== 'Completed') edited = true
      task.State = 'Completed'
      const progress = data.questPolicy?.completedPartialProgress ?? data.counts?.[id] ?? 0
      if (atLeast(task, 'PartialProgress', progress)) edited = true
    }
    if (edited) changed++
  }
  if (names.includes(section.FocusedQuestId)) section.FocusedQuestId = ''
  return { changed, added, notes: [] }
}

// Completing the main story also makes untouched side quests available. Existing
// active/completed side quests and their task progress are left as they are.
export function completeAllQuests(state, data, cutsceneTags = []) {
  checkFormat(state, data)
  const main = questNames(data, 'mainQuests')
  const side = data.sideQuests?.length ? questNames(data, 'sideQuests') : []
  const result = finishQuests(state, data, main)
  const section = state.body.quest
  const existing = indexed(section.Quests, 'QuestName')
  let available = 0
  for (const name of side) {
    let quest = existing.get(name)
    if (quest && ![undefined, 'Unavailable', 'NotSet'].includes(quest.State)) continue
    if (!quest) {
      quest = { QuestName: name, State: 'Available', TaskData: [] }
      section.Quests.push(quest)
      result.added++
    }
    quest.State = 'Available'
    const tasks = arrayField(quest, 'TaskData')
    const byName = indexed(tasks, 'TaskName')
    for (const id of data.quests[name]) {
      if (!byName.has(id))
        tasks.push({
          TaskName: id,
          State: data.questPolicy?.availableTaskState || 'NotSet',
          PartialProgress: 0,
        })
    }
    available++
  }
  const world = objectField(state.body, 'WorldExploration')
  const tags = arrayField(world, 'SavedCutsceneTags')
  const seen = new Set(tags)
  let cutscenesAdded = 0
  for (const tag of cutsceneTags) {
    if (!tag || seen.has(tag)) continue
    tags.push(tag)
    seen.add(tag)
    cutscenesAdded++
  }
  return { ...result, available, cutscenesAdded }
}

export function completeSideQuests(state, data) {
  checkFormat(state, data)
  return finishQuests(state, data, questNames(data, 'sideQuests'))
}

export function unlockAllTravel(state, data) {
  checkFormat(state, data)
  if (!data?.stations?.length) throw new Error('Missing game station data')
  const targets = Object.values(data.travelActors || {}).flat()
  indexed(targets, 'SoftObjectPath')
  const world = objectField(state.body, 'WorldExploration')
  const found = arrayField(world, 'DiscoveredMinecartStationTags')
  const actors = arrayField(world, 'SavedActorStates')
  const byPath = indexed(actors, 'SoftObjectPath')
  const seen = new Set(found)
  let added = 0,
    actorsAdded = 0,
    actorsChanged = 0
  for (const tag of data.stations) {
    if (!seen.has(tag)) {
      found.push(tag)
      seen.add(tag)
      added++
    }
  }
  for (const target of targets) {
    const current = byPath.get(target.SoftObjectPath)
    if (!current) {
      actors.push({ ...target })
      actorsAdded++
    } else {
      if (
        current.PreviousState !== target.PreviousState ||
        current.CurrentState !== target.CurrentState
      )
        actorsChanged++
      current.PreviousState = target.PreviousState
      current.CurrentState = target.CurrentState
      if (current.Version === undefined) current.Version = target.Version
    }
  }
  return { added, actorsAdded, actorsChanged, notes: [] }
}

export const unlockAllWaypoints = unlockAllTravel

export function completeAllAchievements(state, data) {
  checkFormat(state, data)
  if (!data?.achievements || !Object.keys(data.achievements).length)
    throw new Error('Missing verified achievement targets')
  const achievements = objectField(state.body, 'Achievements')
  let changed = 0,
    added = 0
  for (const [kind, targets] of Object.entries(data.achievements)) {
    const records = objectField(achievements, kind)
    for (const [id, target] of Object.entries(targets)) {
      if (!Object.hasOwn(records, id)) {
        records[id] = {}
        added++
      }
      const record = objectField(records, id)
      if (kind === 'CountAchievements') {
        if (atLeast(record, 'Count', target.Count)) changed++
      } else if (kind === 'CollectionAchievements') {
        const found = arrayField(record, 'CollectedTags')
        const seen = new Set(found)
        let edited = false
        for (const tag of target.CollectedTags) {
          if (!seen.has(tag)) {
            found.push(tag)
            seen.add(tag)
            edited = true
          }
        }
        if (edited) changed++
      } else if (['QuestAchievements', 'BoolAchievements'].includes(kind)) {
        if (record.bCompleted !== true) {
          record.bCompleted = true
          changed++
        }
      } else throw new Error('Unsupported achievement category: ' + kind)
    }
  }
  return { changed, added, notes: [] }
}

// ---------------------------------------------------------- map fog of war

const CLEAR = 255
const MOST_SQUARES = 20000

const KNOWN_REGIONS = [
  { tag: 'SW.Region.Camp', corner: [-2720, -192], size: [16, 16] },
  { tag: 'SW.Region.Overworld', corner: [-608, -192], size: [52, 52] },
  { tag: 'SW.Area.Meadow.R0', corner: [-704, 1184], size: [12, 12] },
  { tag: 'SW.Area.Meadow.R1', corner: [-928, 1184], size: [16, 12] },
  { tag: 'SW.Area.Forest.A1.Underwell', corner: [-544, 32], size: [4, 4] },
  { tag: 'SW.Area.Plains.A1.ScoutPoint', corner: [-544, 224], size: [4, 4] },
  { tag: 'SW.Area.Forest.A1.WitchInt', corner: [-2208, -960], size: [4, 4] },
  { tag: 'SW.Area.Plains.A2.NatInteriors', corner: [-576, 1024], size: [16, 16] },
  { tag: 'SW.Area.Plains.A2.RavagerTower', corner: [-1440, -448], size: [16, 16] },
  { tag: 'SW.Area.Plains.A2.CampTower', corner: [-1440, -544], size: [16, 16] },
  { tag: 'SW.Area.Plains.A2.StorageTower', corner: [-1440, -128], size: [16, 16] },
  { tag: 'SW.Area.Plains.A2.BossTower', corner: [-256, 128], size: [4, 4] },
  { tag: 'SW.Area.Plains.A2.BossArena', corner: [-256, 384], size: [4, 4] },
  { tag: 'SW.Area.Plains.A2.NoteblockRoom', corner: [-1408, 96], size: [4, 4] },
  { tag: 'Sw.Area.Plains.A1.SpookyBarnBasement', corner: [-672, -576], size: [4, 4] },
  { tag: 'SW.Area.Desert.A1.ShipInt', corner: [-1600, 384], size: [16, 16] },
  { tag: 'SW.Area.Desert.A1.Basement', corner: [-2336, 352], size: [20, 20] },
  { tag: 'SW.Area.Desert.A1.FortHalls', corner: [-928, 224], size: [12, 12] },
  { tag: 'SW.Area.Desert.A1.Tower', corner: [-576, 352], size: [4, 4] },
  { tag: 'SW.Region.Sift', corner: [-1120, 1536], size: [44, 44] },
  { tag: 'SW.Area.Carapace.A1.CarapaceInterior', corner: [-2496, -608], size: [12, 12] },
  { tag: 'SW.Area.DeepDark.A2.PortalEntry', corner: [-2624, 2560], size: [8, 8] },
  { tag: 'SW.Area.Desert.A1.QuestTowers', corner: [-1984, 96], size: [12, 12] },
  { tag: 'SW.Area.Meadow.A1.NatInteriors', corner: [-480, 1504], size: [20, 20] },
  { tag: 'SW.Area.Meadow.A2.MeadowFortress', corner: [-2016, 2592], size: [12, 12] },
  { tag: 'SW.Area.Desert.A1.Watchtower', corner: [-1024, 384], size: [4, 4] },
]

function fogSquares(item) {
  const size = item?.Size
  const across = size?.X
  const down = size?.Y
  const whole = Number.isInteger(across) && Number.isInteger(down) && across > 0 && down > 0
  return whole && across * down <= MOST_SQUARES && Array.isArray(item?.Data) ? across * down : 0
}

export function discoverAllMap(state, data, mapPoints) {
  const place = state.body?.WorldExploration
  const fog = place?.SavedFogOfWarExploration
  const items = fog?.Items
  if (!Array.isArray(items))
    return { cleared: 0, added: 0, notes: ['no map data (play until the game draws one)'] }

  let cleared = 0
  for (const item of items) {
    const n = fogSquares(item)
    if (n && (item.Data.length !== n || item.Data.some((value) => value !== CLEAR))) {
      item.Data = Array.from({ length: n }, () => CLEAR)
      cleared++
    }
  }

  const have = new Set(items.map((i) => i?.Tag).filter(Boolean))
  let added = 0
  for (const region of KNOWN_REGIONS) {
    if (have.has(region.tag)) continue
    const [x, y] = region.corner
    const [across, down] = region.size
    items.push({
      Tag: region.tag,
      Data: Array.from({ length: across * down }, () => CLEAR),
      WorldPosition: { X: x, Y: y },
      Size: { X: across, Y: down },
    })
    added++
  }

  // Map markers (dungeon doors, rifts, towers) are separate from fog-of-war.
  // The bundled seeds carry the exact marker types and overrides. Story cutscenes
  // belong to the main-story completion button instead.
  const world = objectField(state.body, 'WorldExploration')
  const doors = arrayField(world, 'DiscoveredDungeonDoors')
  const doorIds = new Set(doors.map((d) => d?.DoorId))
  let doorsAdded = 0
  for (const door of mapPoints?.doors || []) {
    if (!door?.DoorId || doorIds.has(door.DoorId)) continue
    doors.push(JSON.parse(JSON.stringify(door)))
    doorIds.add(door.DoorId)
    doorsAdded++
  }
  const travel = data?.stations?.length ? unlockAllTravel(state, data) : null
  return {
    cleared,
    added,
    doorsAdded,
    stationsAdded: travel?.added || 0,
    actorsAdded: travel?.actorsAdded || 0,
    actorsChanged: travel?.actorsChanged || 0,
    notes: [],
  }
}
