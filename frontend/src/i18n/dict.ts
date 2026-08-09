// UI chrome copy only. Generated content (dialogue, scene titles) comes from
// the LLM and is never routed through here.
//
// Chinese is the default: the primary demo audience is Chinese-speaking, and
// the CJK-first constraint in docs/v4/PRODUCT_v4.md applies to the shell too.
export const dict = {
  zh: {
    // ── ChatPanel ──
    'chat.settings': '生成设置',
    'chat.scenes': '场景数',
    'chat.characters': '角色数',
    'chat.textOnly': '仅文本',
    'chat.fastMode': '快速模式',
    'chat.mock': 'Mock（零 API 花费）',
    'chat.mockNotice': 'Mock 模式已开启——本次生成使用预置样例数据，不会产生任何真实 API 调用或花费。',
    'chat.feedback': '反馈',
    'chat.placeholderTheme': '输入你的故事主题…',
    'chat.placeholderChatOps': '提问，或要求改写某一场…',
    'chat.send': '发送',
    'chat.sending': '处理中…',
    'chat.autopilot': '一键生成',
    'chat.autopilotHint': '跳过所有确认步骤，直接进入播放器',
    'chat.retry': '重新生成',
    'chat.confirm': '确认执行',
    'chat.cancel': '取消',
    'chat.running': '执行中…',
    'chat.confidence': '置信度',
    'intent.local_regen': '改写场景',
    'intent.add_character': '新增角色',
    'intent.edit_asset': '修改素材',
    'intent.unknown': '未识别意图',
    // ── VNPreview ──
    'vn.backToEditor': '返回工作台',
    'vn.clickToStart': '点击开始',
    'vn.clickToContinue': '点击继续',
    'vn.fin': '完',
    'vn.scene': '场景',
    'vn.line': '对白',
    // ── 语言开关 ──
    'lang.toggle': 'EN',
    'lang.toggleHint': 'Switch to English',
  },
  en: {
    // ── ChatPanel ──
    'chat.settings': 'Settings',
    'chat.scenes': 'Scenes',
    'chat.characters': 'Characters',
    'chat.textOnly': 'Text Only',
    'chat.fastMode': 'Fast Mode',
    'chat.mock': 'Mock (Zero API $)',
    'chat.mockNotice': 'Mock mode is on — this generation uses canned fixture responses; no real API calls, no token spend.',
    'chat.feedback': 'Feedback',
    'chat.placeholderTheme': 'Enter your story theme…',
    'chat.placeholderChatOps': 'Ask a question, or ask to rewrite a scene…',
    'chat.send': 'Send',
    'chat.sending': 'Working…',
    'chat.autopilot': 'Autopilot',
    'chat.autopilotHint': 'Skip review steps and jump straight into the player',
    'chat.retry': 'Retry generation',
    'chat.confirm': 'Confirm',
    'chat.cancel': 'Cancel',
    'chat.running': 'Running…',
    'chat.confidence': 'confidence',
    'intent.local_regen': 'Rewrite scene',
    'intent.add_character': 'Add character',
    'intent.edit_asset': 'Edit asset',
    'intent.unknown': 'Unrecognised intent',
    // ── VNPreview ──
    'vn.backToEditor': 'Back to Editor',
    'vn.clickToStart': 'Click to start',
    'vn.clickToContinue': 'Click to continue',
    'vn.fin': 'Fin',
    'vn.scene': 'Scene',
    'vn.line': 'Line',
    // ── language switch ──
    'lang.toggle': '中',
    'lang.toggleHint': '切换到中文',
  },
} as const

export type Lang = keyof typeof dict
export type TKey = keyof (typeof dict)['zh']
