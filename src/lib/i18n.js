// Lightweight i18n: reactive locale + flat key lookup. Browser language auto-detected;
// data strings (item/effect names) already come bilingual from catalog.json + zh.json.
import { ref, shallowRef } from 'vue'
import { POOL_ZH, ROLL_SLOT_LABELS } from './catalog.js'
export { classColor, poolColor, slotColor } from './tag-colors.js'

export const locale = ref(globalThis.navigator?.language?.startsWith('zh') ? 'zh' : 'en')
const dataLabels = shallowRef({})

export function setDataLabels(labels) {
  dataLabels.value = labels || {}
}

function dataLabel(group, id) {
  const label = dataLabels.value[group]?.[id]
  return typeof label === 'string' ? label : label?.[locale.value]
}

const zh = {
  'file.conflict': '存档已被游戏或其他窗口修改。可先导出副本，再重新读取磁盘存档。',
  'file.reload': '重新读取',
  'file.forceSave': '强制保存',
  'app.name': '存档编辑器',
  'file.starter': '初始存档',
  'file.starterHint': '初始存档 · 请从 %LOCALAPPDATA%\\Dungeons2\\Saved\\SaveGames 导入 Character*.sav',
  'file.onDisk': '存档目录',
  'file.discard': '放弃当前未保存的修改并打开其他存档？',
  'file.invalid': '无法读取英雄存档',
  'file.copy': '导出副本',
  'file.export': '导出存档',
  'status.clean': '已同步',
  'status.noChange': '没有需要修改的内容。',
  'status.undone': '已撤销上一步。',
  'status.download': '已导出存档。',
  'status.backup': '已写入。备份位于',
  'status.saved': '已保存。',
  'status.skipped': '已跳过',
  'list.inventory': '装备栏',
  'list.other': '其他',
  'detail.mixed': '所选装备的档位不同',
  'detail.selected': '件装备已选',
  'detail.shared': '共有词条',
  'detail.applyTip': '用当前可重洗词条替换同部位、同词条池装备的词条',
  'detail.enchantTip': '将当前附魔或空槽同步到同类装备',
  'nav.editor': '编辑器',
  'nav.batch': '批量工具',
  'nav.pools': '词条总览',
  'nav.unlock': '解锁',
  'nav.undo': '撤销',
  'nav.save': '保存',
  'nav.import': '导入存档',
  'nav.dirty': '有未保存的改动',
  'nav.unlockTip': '解除词条池、部位和数量限制',

  'common.all': '全部',
  'common.close': '关闭',
  'common.copy': '复制',
  'common.delete': '删除',
  'common.remove': '移除',

  'editor.selectItem': '在左侧选择一件装备。',
  'editor.empty': '装备栏为空',
  'editor.addGear': '从批量工具添加装备',

  'detail.ownFx': '独特词条',
  'detail.effects': '可洗词条',
  'detail.noRolled': '暂无词条',
  'detail.enchant': '附魔',
  'detail.candidateEnchants': '候选附魔',
  'detail.enchantArmor': '护甲',
  'detail.mixedEnchant': '所选装备的附魔不同。',
  'detail.noOtherEnchant': '没有其他候选附魔',
  'detail.noEnchantArtifact': '法器不能附魔',
  'detail.noEnchant': '没有适用的附魔',
  'detail.addEnchantHint': '暂无附魔',
  'detail.apply': '应用同类',
  'detail.applyEnchant': '附魔同类',
  'detail.equipped': '已装备',
  'detail.stock': '商店存货',
  'detail.storm': '风暴',
  'detail.level': '等级',
  'detail.rarCommon': '普通',
  'detail.rarRare': '稀有',
  'detail.rarSpecial': '特殊',
  'detail.rarUnique': '独特',
  'detail.noUnique': '该装备没有独特稀有度',
  'detail.addOwn': '追加独特词条',

  'picker.title': '可选词条',
  'picker.rollsTab': '词条',
  'picker.talismanTab': '护符',
  'detail.slots': '原版适用部位',
  'detail.pools': '词条池',
  'picker.empty': '所选装备没有共同适用的词条。',
  'picker.add': '添加最高可用档位',

  'unique.title': '选择独特词条',
  'unique.search': '搜索词条 / 装备...',
  'unique.swap': '更换',
  'unique.pick': '更换为任意独特词条',
  'unique.empty': '没有匹配的独特词条',
  'unique.append': '追加',

  'list.search': '搜索装备名 / ID...',
  'list.noMatch': '没有匹配的装备',
  'list.empty': '添加或导入的装备会显示在这里。',

  'batch.title': '批量工具',
  'batch.scope': '仅作用于选定部位',
  'batch.hero': '英雄',
  'batch.maxStats': '满级满资源',
  'batch.quests': '全主线完成',
  'batch.questsTip': '完成全部主线，并使未解锁的支线可用；保留已有支线进度。',
  'batch.sideQuests': '全支线完成',
  'batch.achievements': '全成就完成',
  'batch.travel': '全传送解锁',
  'batch.travelTip': '解锁全部车站，并打开大门与捷径。',
  'batch.map': '全地图探索',
  'batch.slot': '部位',
  'batch.gear': '装备',
  'batch.clear': '清空该部位装备',
  'batch.addUnique': '添加所有独特装备',
  'batch.addArtifact': '添加所有法器',
  'batch.addTalisman': '添加所有护身符',
  'batch.addBook': '添加所有附魔书',
  'batch.rarity': '稀有度',
  'batch.setAll': '全部设为',
  'batch.noRarity': '护身符与附魔书没有稀有度',
  'batch.storm': '风暴标志',
  'batch.noStorm': '护身符与附魔书不能带风暴标志',
  'batch.addStorm': '添加风暴标志',
  'batch.clearStorm': '清除风暴标志',
  'batch.talismanLevel': '护身符等级',
  'batch.power': '能量 / 等级',
  'batch.noLevel': '附魔书没有等级',
  'batch.setLevel': '全部设为该等级',
  'batch.confirmClear': '清空',
  'batch.confirmClearMsg': '的',
  'batch.confirmClearEnd': '件装备（含已装备物品）？此操作可撤销。',
  'batch.slotMelee': '近战',
  'batch.slotRanged': '远程',
  'batch.slotHelmet': '头盔',
  'batch.slotChest': '胸甲',
  'batch.slotLeggings': '护腿',
  'batch.slotBoots': '靴子',
  'batch.slotArtifact': '法器',
  'batch.slotTalisman': '护身符',
  'batch.slotBook': '附魔书',
}

const en = {
  'file.conflict': 'The save changed on disk. Export a copy of your edits or reopen the disk save.',
  'file.reload': 'Reopen save',
  'file.forceSave': 'Save Anyway',
  'app.name': 'Save Editor',
  'file.starter': 'Starter save',
  'file.starterHint': 'Starter save · import your Character*.sav from %LOCALAPPDATA%\\Dungeons2\\Saved\\SaveGames',
  'file.onDisk': 'Save directory',
  'file.discard': 'Discard unsaved changes and open another save?',
  'file.invalid': 'Could not read this hero save',
  'file.copy': 'Export copy',
  'file.export': 'Export save',
  'status.clean': 'Up to date',
  'status.noChange': 'Nothing to change.',
  'status.undone': 'Last edit undone.',
  'status.download': 'Save exported.',
  'status.backup': 'Saved. Backup in',
  'status.saved': 'Saved.',
  'status.skipped': 'Skipped',
  'list.inventory': 'Inventory',
  'list.other': 'Other',
  'detail.mixed': 'Tiers differ across the selection',
  'detail.selected': 'items selected',
  'detail.shared': 'Shared rolls',
  'detail.applyTip': 'Replace rolls on items with the same slot and effect pool',
  'detail.enchantTip': 'Copy the current enchantment or empty slot to matching items',
  'nav.editor': 'Editor',
  'nav.batch': 'Batch Tools',
  'nav.pools': 'Effect guide',
  'nav.unlock': 'Unlock',
  'nav.undo': 'Undo',
  'nav.save': 'Save',
  'nav.import': 'Import Save',
  'nav.dirty': 'Unsaved changes',
  'nav.unlockTip': 'Lift effect pool, slot and count limits',

  'common.all': 'All',
  'common.close': 'Close',
  'common.copy': 'Copy',
  'common.delete': 'Delete',
  'common.remove': 'Remove',

  'editor.selectItem': 'Select an item on the left.',
  'editor.empty': 'Your inventory is empty',
  'editor.addGear': 'Add gear in Batch Tools',

  'detail.ownFx': 'Unique effects',
  'detail.effects': 'Rolled effects',
  'detail.noRolled': 'No rolled effects',
  'detail.enchant': 'Enchantment',
  'detail.candidateEnchants': 'Available enchantments',
  'detail.enchantArmor': 'Armor',
  'detail.mixedEnchant': 'Selected items have different enchantments.',
  'detail.noOtherEnchant': 'No other enchantments available',
  'detail.noEnchantArtifact': 'Artifacts cannot be enchanted',
  'detail.noEnchant': 'No enchantments available',
  'detail.addEnchantHint': 'Click + below to add an enchantment, then pick a tier',
  'detail.apply': 'Apply Same',
  'detail.applyEnchant': 'Enchant Same',
  'detail.equipped': 'equipped',
  'detail.stock': 'merchant stock',
  'detail.storm': 'Storm',
  'detail.level': 'Lv.',
  'detail.rarCommon': 'Common',
  'detail.rarRare': 'Rare',
  'detail.rarSpecial': 'Special',
  'detail.rarUnique': 'Unique',
  'detail.noUnique': 'This gear has no Unique rarity',
  'detail.addOwn': 'Add unique effect',

  'picker.title': 'Available rolls',
  'picker.rollsTab': 'Rolls',
  'picker.talismanTab': 'Talismans',
  'detail.slots': 'Native equipment slots',
  'detail.pools': 'Effect pool',
  'picker.empty': 'No rolls fit the current selection.',
  'picker.add': 'Add the highest available tier',

  'unique.title': 'Choose a unique effect',
  'unique.search': 'Search effect / gear...',
  'unique.swap': 'Swap',
  'unique.pick': 'Swap with any unique effect',
  'unique.empty': 'No matching unique effects',
  'unique.append': 'Append',

  'list.search': 'Search name / ID...',
  'list.noMatch': 'No matching items',
  'list.empty': 'Gear you add or import will appear here.',

  'batch.title': 'Batch Tools',
  'batch.scope': 'Applies to all items in the same slot',
  'batch.hero': 'Hero',
  'batch.maxStats': 'Max Level + All Resources',
  'batch.quests': 'Complete All Main Quests',
  'batch.questsTip':
    'Complete the main story and make locked side quests available, preserving existing side-quest progress.',
  'batch.sideQuests': 'Complete All Side Quests',
  'batch.achievements': 'Complete All Achievements',
  'batch.travel': 'Unlock All Travel',
  'batch.travelTip': 'Unlock every station and open gates and shortcuts.',
  'batch.map': 'Explore Full Map',
  'batch.slot': 'Slot',
  'batch.gear': 'Gear',
  'batch.clear': 'Clear This Slot',
  'batch.addUnique': 'Add All Uniques',
  'batch.addArtifact': 'Add All Artifacts',
  'batch.addTalisman': 'Add All Talismans',
  'batch.addBook': 'Add All Enchantment Books',
  'batch.rarity': 'Rarity',
  'batch.setAll': 'Set All To',
  'batch.noRarity': 'Talismans and books have no rarity',
  'batch.storm': 'Storm Flag',
  'batch.noStorm': 'Talismans and books cannot have storm flag',
  'batch.addStorm': 'Add Storm Flag',
  'batch.clearStorm': 'Clear Storm Flag',
  'batch.talismanLevel': 'Talisman Level',
  'batch.power': 'Power / Level',
  'batch.noLevel': 'Books have no level',
  'batch.setLevel': 'Set All To This Level',
  'batch.confirmClear': 'Clear',
  'batch.confirmClearMsg': ' ',
  'batch.confirmClearEnd': ' items, including equipped gear? You can undo this.',
  'batch.slotMelee': 'Melee',
  'batch.slotRanged': 'Ranged',
  'batch.slotHelmet': 'Helmet',
  'batch.slotChest': 'Chest',
  'batch.slotLeggings': 'Leggings',
  'batch.slotBoots': 'Boots',
  'batch.slotArtifact': 'Artifact',
  'batch.slotTalisman': 'Talisman',
  'batch.slotBook': 'Enchantment Book',
}

// Label maps for data categories (kind / piece / class / pool / effect-category)
const KIND = {
  zh: { Melee: '近战', Ranged: '远程', Armor: '盔甲', Artifact: '法器' },
  en: {
    Melee: 'Melee',
    Ranged: 'Ranged',
    Armor: 'Armor',
    Artifact: 'Artifact',
  },
}
const PIECE = {
  zh: { helmet: '头盔', chest: '胸甲', leggings: '护腿', boots: '靴子' },
  en: {
    helmet: 'Helmet',
    chest: 'Chest',
    leggings: 'Leggings',
    boots: 'Boots',
  },
}
const CLASS = {
  zh: {
    Fighter: '战士',
    Ranger: '游侠',
    Mage: '法师',
    Tank: '坦克',
    Support: '辅助',
    Summoner: '召唤',
    Trickster: '诡术',
    Utility: '通用',
  },
  en: {
    Fighter: 'Fighter',
    Ranger: 'Ranger',
    Mage: 'Mage',
    Tank: 'Tank',
    Support: 'Support',
    Summoner: 'Summoner',
    Trickster: 'Trickster',
    Utility: 'Utility',
  },
}
const CATEGORY = {
  zh: { offensive: '攻击', defensive: '防御', utility: '实用', other: '其他' },
  en: { offensive: 'Attack', defensive: 'Defense', utility: 'Utility', other: 'Other' },
}

const messages = { zh, en }

export function kindLabel(k) {
  return KIND[locale.value]?.[k] || k
}
export function pieceLabel(p) {
  return PIECE[locale.value]?.[p] || p
}
export function classLabel(c) {
  return dataLabel('pools', 'Archetype.' + c) || CLASS[locale.value]?.[c] || c
}
export function poolLabel(p) {
  return dataLabel('pools', p) || (locale.value === 'zh' && POOL_ZH[p]) || p.split('.').pop()
}
export function slotLabel(slot) {
  return ROLL_SLOT_LABELS[slot]?.[locale.value] || slot
}
export function categoryLabel(c) {
  return dataLabel('categories', c) || CATEGORY[locale.value]?.[c] || c
}

const RARITY_KEYS = {
  Common: 'detail.rarCommon',
  Rare: 'detail.rarRare',
  Special: 'detail.rarSpecial',
  Unique: 'detail.rarUnique',
}
export function rarityLabel(r) {
  const key = RARITY_KEYS[r]
  return key ? t(key) : r
}

export function t(key) {
  return messages[locale.value]?.[key] ?? messages.zh[key] ?? key
}

export function setLocale(l) {
  locale.value = l
}
