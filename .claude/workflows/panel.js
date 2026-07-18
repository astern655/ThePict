export const meta = {
  name: 'panel',
  description: '제안 3안 → 축별 채점 → 적대적 반증 → 종합. 프롬프트 하나를 서로 검증·평가하는 패널에 태운다.',
  whenToUse: '답이 하나로 정해지지 않은 문제(설계 선택, 접근법 비교, 리스크 판단)에서 혼자 답하는 것보다 교차 검증이 필요할 때.',
  phases: [
    { title: 'Propose', detail: '서로 다른 관점 3개로 독립 제안' },
    { title: 'Judge', detail: '제안마다 3개 축으로 병렬 채점' },
    { title: 'Verify', detail: '승자의 핵심 주장을 반박 전용 검증자 3명이 반증 시도' },
    { title: 'Synthesize', detail: '살아남은 주장으로 최종안 작성' },
  ],
}

const question =
  typeof args === 'string' ? args : (args && (args.question || args.prompt)) || ''

if (!question.trim()) {
  return { error: 'args로 질문 문자열을 전달해야 한다.' }
}

// ── 역할 프롬프트 ─────────────────────────────────────────────────────────
// .claude/agents/panel-{proposer,critic,judge}.md 와 같은 역할을 정의한다.
// 커스텀 에이전트는 세션 시작 시에만 등록되므로, 워크플로가 재시작 없이 돌도록
// 여기에 직접 내장한다. 역할을 고칠 때는 양쪽을 함께 고칠 것.
const ROLE_PROPOSER = `너는 심사 패널의 제안자다.
- 배정받은 관점 하나에만 충실하라. 균형을 잡으려 하지 마라. 다른 관점은 다른 제안자가 맡는다.
- 답을 쓰기 전에 근거를 실제로 확인하라. 코드 질문이면 파일을 읽고, 사실 질문이면 검색하라.
- 확신이 낮은 부분은 낮다고 명시하라. 뒤에서 검증자가 반박을 시도한다.
- 근거는 확인 가능한 형태로: 파일은 경로:줄번호, 웹은 URL.`

const ROLE_JUDGE = `너는 심사 패널의 채점자다.
- 배정받은 평가축 하나로만 0–10점을 매겨라. 다른 제안과 비교하지 마라.
- 점수 근거를 확인하라. 인상만으로 점수를 주지 마라.
- 점수 인플레를 경계하라. 5점이 "쓸 만함"의 기준선이고, 8점 이상은 그 축에서 실제로 뛰어날 때만 준다.
- 문체나 분량이 아니라 내용의 타당성을 본다.`

const ROLE_CRITIC = `너는 심사 패널의 검증자다. 임무는 평가가 아니라 반증이다.
- 주어진 주장이 틀렸다고 가정하고 시작하라. 반례, 놓친 조건, 사실 오류, 미검증 전제를 찾아라.
- 근거를 직접 확인하라. 파일을 열지 않고 내린 반박은 무효다.
- 반박 근거를 못 찾은 경우에만 통과시켜라. "그럴듯해 보인다"는 통과 사유가 아니다.
- 애매하면 refuted: true로 판정하라. 통과 기준이 반박 기준보다 엄격해야 한다.
- 제안자의 자신감 있는 어조에 휘둘리지 마라. 문장이 아니라 근거를 본다.`

// ── 관점: 서로 겹치지 않아야 다양성이 산출된다 ────────────────────────────
const LENSES = [
  {
    key: 'minimal',
    label: '최소구현',
    brief: '가장 단순하고 빨리 되는 안. 범위를 깎는 쪽으로 판단하고, 지금 필요 없는 것은 전부 뺀다.',
  },
  {
    key: 'robust',
    label: '견고성',
    brief: '실패 모드·엣지케이스·유지보수를 우선하는 안. 나중에 무너질 지점을 미리 막는다.',
  },
  {
    key: 'user',
    label: '사용자관점',
    brief: '실제 사용 흐름과 체감을 우선하는 안. 기술적 우아함보다 쓰는 사람의 마찰을 줄인다.',
  },
]

const AXES = [
  { key: 'correct', label: '정확성', brief: '사실과 근거가 맞는가. 틀린 전제 위에 서 있지 않은가.' },
  { key: 'feasible', label: '실행가능성', brief: '이 환경에서 실제로 실행 가능한가. 숨은 선행조건은 없는가.' },
  { key: 'fit', label: '요구부합', brief: '질문자가 실제로 물은 것에 답하는가. 범위를 벗어나거나 미달하지 않는가.' },
]

const PROPOSAL_SCHEMA = {
  type: 'object',
  required: ['summary', 'claims', 'risks'],
  additionalProperties: false,
  properties: {
    summary: { type: 'string', description: '제안의 핵심을 3문장 이내로' },
    body: { type: 'string', description: '제안 본문 (마크다운)' },
    claims: {
      type: 'array',
      description: '이 제안이 성립하기 위해 참이어야 하는 핵심 주장들. 최대 5개.',
      maxItems: 5,
      items: {
        type: 'object',
        required: ['claim', 'evidence'],
        additionalProperties: false,
        properties: {
          claim: { type: 'string' },
          evidence: { type: 'string', description: '근거. 파일은 경로:줄번호, 웹은 URL.' },
        },
      },
    },
    risks: { type: 'array', items: { type: 'string' }, maxItems: 5 },
  },
}

const SCORE_SCHEMA = {
  type: 'object',
  required: ['score', 'reason'],
  additionalProperties: false,
  properties: {
    score: { type: 'number', minimum: 0, maximum: 10 },
    reason: { type: 'string', description: '점수 근거 2문장 이내' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['refuted', 'reason'],
  additionalProperties: false,
  properties: {
    refuted: { type: 'boolean', description: '반박에 성공했거나 근거 확인 불가면 true' },
    reason: { type: 'string' },
    counterexample: { type: 'string' },
  },
}

// ── 1~2단계: 제안과 채점을 파이프라인으로. 배리어 없이 각 안이 끝나는 대로 채점된다 ──
phase('Propose')

const scored = await pipeline(
  LENSES,
  (lens) =>
    agent(
      `${ROLE_PROPOSER}\n\n---\n\n다음 질문에 "${lens.label}" 관점으로만 답하라.\n\n관점 정의: ${lens.brief}\n\n` +
        `질문:\n${question}\n\n` +
        `claims에는 이 제안이 무너지지 않으려면 반드시 참이어야 하는 주장만 넣어라. ` +
        `뒤에서 반박 전용 검증자가 이 claims를 하나씩 반증 시도한다.`,
      {
        label: `propose:${lens.key}`,
        phase: 'Propose',
        schema: PROPOSAL_SCHEMA,
      },
    ),
  async (proposal, lens) => {
    if (!proposal) return null
    const scores = await parallel(
      AXES.map((axis) => () =>
        agent(
          `${ROLE_JUDGE}\n\n---\n\n아래 제안을 "${axis.label}" 축으로만 채점하라 (0–10).\n\n축 정의: ${axis.brief}\n\n` +
            `원 질문:\n${question}\n\n` +
            `제안 (${lens.label} 관점):\n${proposal.summary}\n\n${proposal.body || ''}\n\n` +
            `핵심 주장:\n${proposal.claims.map((c, i) => `${i + 1}. ${c.claim} — 근거: ${c.evidence}`).join('\n')}`,
          {
            label: `judge:${lens.key}/${axis.key}`,
            phase: 'Judge',
            schema: SCORE_SCHEMA,
          },
        ),
      ),
    )
    const valid = scores.filter(Boolean)
    if (!valid.length) return null
    const total = valid.reduce((sum, s) => sum + s.score, 0) / valid.length
    return { lens, proposal, scores: valid, total }
  },
)

const ranked = scored.filter(Boolean).sort((a, b) => b.total - a.total)

if (!ranked.length) {
  return { error: '모든 제안이 실패했다. 질문이 너무 모호하거나 에이전트가 전부 오류로 종료됐다.' }
}

const winner = ranked[0]
const runnersUp = ranked.slice(1)
log(`승자: ${winner.lens.label} (평균 ${winner.total.toFixed(1)}점)`)

// ── 3단계: 승자의 주장을 반박 전용 검증자 3명이 각각 반증 시도. 2표 이상 반박이면 탈락 ──
phase('Verify')

const REFUTERS = 3
const MAX_CLAIMS = 3 // 검증 비용 상한. 초과분은 아래 log로 드러낸다.
const toVerify = winner.proposal.claims.slice(0, MAX_CLAIMS)
if (winner.proposal.claims.length > MAX_CLAIMS) {
  log(`주장 ${winner.proposal.claims.length}개 중 상위 ${MAX_CLAIMS}개만 검증 (나머지는 미검증)`)
}

const verified = await parallel(
  toVerify.map((c, i) => () =>
    parallel(
      Array.from({ length: REFUTERS }, (_, r) => () =>
        agent(
          `${ROLE_CRITIC}\n\n---\n\n다음 주장을 반증하라. 동의를 구하는 것이 아니라 틀렸음을 보이는 것이 임무다.\n\n` +
            `주장: ${c.claim}\n제시된 근거: ${c.evidence}\n\n` +
            `맥락 — 원 질문:\n${question}\n\n` +
            `근거를 직접 확인하라. 확인할 수 없으면 refuted: true다. ` +
            `검증자 ${r + 1}번으로서 다른 검증자와 독립적으로 판단하라.`,
          {
            label: `refute:${i + 1}#${r + 1}`,
            phase: 'Verify',
            schema: VERDICT_SCHEMA,
          },
        ),
      ),
    ).then((votes) => {
      const valid = votes.filter(Boolean)
      const refutedCount = valid.filter((v) => v.refuted).length
      // 응답이 부족하면 통과시키지 않는다 — 침묵은 검증이 아니다.
      const survived = valid.length >= 2 && refutedCount < Math.ceil(valid.length / 2)
      return { ...c, survived, refutedCount, votes: valid }
    }),
  ),
)

const survivingClaims = verified.filter(Boolean).filter((v) => v.survived)
const killedClaims = verified.filter(Boolean).filter((v) => !v.survived)
log(`주장 검증: ${survivingClaims.length}개 생존 / ${killedClaims.length}개 탈락`)

// ── 4단계: 종합 ────────────────────────────────────────────────────────
phase('Synthesize')

const finalAnswer = await agent(
  `아래 패널 심사 결과를 바탕으로 원 질문에 대한 최종 답변을 한국어 마크다운으로 작성하라.\n\n` +
    `원 질문:\n${question}\n\n` +
    `## 승자 (${winner.lens.label}, 평균 ${winner.total.toFixed(1)}점)\n${winner.proposal.summary}\n\n${winner.proposal.body || ''}\n\n` +
    `## 검증 통과한 주장\n` +
    (survivingClaims.map((c) => `- ${c.claim} (근거: ${c.evidence})`).join('\n') || '- 없음') +
    `\n\n## 반박되어 탈락한 주장 — 최종 답변의 근거로 쓰지 마라\n` +
    (killedClaims
      .map((c) => `- ${c.claim}\n  반박 사유: ${c.votes.filter((v) => v.refuted).map((v) => v.reason).join(' / ')}`)
      .join('\n') || '- 없음') +
    `\n\n## 탈락한 다른 관점의 안 — 승자에 없는 좋은 아이디어가 있으면 흡수하라\n` +
    runnersUp.map((r) => `### ${r.lens.label} (평균 ${r.total.toFixed(1)}점)\n${r.proposal.summary}`).join('\n\n') +
    `\n\n## 지적된 리스크\n` +
    (winner.proposal.risks.map((r) => `- ${r}`).join('\n') || '- 없음') +
    `\n\n작성 규칙:\n` +
    `- 탈락한 주장은 근거로 쓰지 마라. 그 주제를 다뤄야 한다면 불확실하다고 명시하라.\n` +
    `- 심사 과정을 설명하지 말고 질문에 직접 답하라.\n` +
    `- 마지막에 "## 남은 불확실성" 절을 두고, 검증에서 탈락했거나 확인되지 않은 지점을 정직하게 적어라.`,
  { label: 'synthesize', phase: 'Synthesize' },
)

return {
  answer: finalAnswer,
  winner: winner.lens.label,
  ranking: ranked.map((r) => ({ lens: r.lens.label, score: Number(r.total.toFixed(1)) })),
  claimsSurvived: survivingClaims.length,
  claimsRefuted: killedClaims.length,
}
